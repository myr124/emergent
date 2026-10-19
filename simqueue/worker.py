"""Worker pool that drains the persona job queue.

    python -m simqueue.worker                 # WORKER_PROCESSES x WORKER_CONCURRENCY
    python -m simqueue.worker -p 4 -c 10      # 4 processes, 10 concurrent jobs each

Each process registers itself with a heartbeat. Jobs are moved atomically from
the shared queue onto the process's own processing list and removed only once
handled, and every process periodically requeues jobs held by workers whose
heartbeat has expired.
"""

import argparse
import asyncio
import json
import logging
import multiprocessing
import os
import signal
import socket
import uuid
from typing import Any, Awaitable, Callable, Dict

from dotenv import load_dotenv
from redis.asyncio import Redis

from . import config, store

log = logging.getLogger("simqueue.worker")

RunPersona = Callable[[str, str], Awaitable[Dict[str, Any]]]


def _is_retryable(exc: BaseException) -> bool:
    # Client errors (bad API key, invalid request) fail the same way every time;
    # rate limits, timeouts, server errors and malformed model output may not.
    code = getattr(exc, "code", None)
    if isinstance(code, int) and 400 <= code < 500:
        return code in (408, 429)
    return True


class Worker:
    def __init__(
        self,
        redis: Redis,
        specs: Dict[str, Dict[str, str]],
        run_persona: RunPersona,
        concurrency: int = config.WORKER_CONCURRENCY,
    ):
        self.redis = redis
        self.specs = specs
        self.run_persona = run_persona
        self.concurrency = concurrency
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.stopping = asyncio.Event()

    async def run(self) -> None:
        await self._heartbeat_once()
        background = [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._reap_loop()),
        ]
        consumers = [asyncio.create_task(self._consume()) for _ in range(self.concurrency)]
        log.info("worker %s started with %d consumers", self.id, self.concurrency)
        try:
            await asyncio.gather(*consumers)
        finally:
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            # Anything still on our processing list goes back to the queue now
            # rather than waiting for another worker's reaper.
            await self._requeue_from(self.id)
            await self.redis.delete(store.heartbeat_key(self.id))
            await self.redis.srem(store.WORKERS, self.id)
            log.info("worker %s stopped", self.id)

    def stop(self) -> None:
        self.stopping.set()

    async def _consume(self) -> None:
        processing = store.processing_key(self.id)
        while not self.stopping.is_set():
            raw = await self.redis.blmove(store.QUEUE, processing, 1, "RIGHT", "LEFT")
            if raw is None:
                continue
            try:
                await self._handle(json.loads(raw))
            except Exception:
                log.exception("unhandled error for job %s", raw)
            finally:
                await self.redis.lrem(processing, 1, raw)

    async def _handle(self, job: Dict[str, Any]) -> None:
        sim_id, persona = job["sim_id"], job["persona"]
        prompt = await self.redis.get(store.prompt_key(sim_id))
        spec = self.specs.get(persona)
        if prompt is None or spec is None:
            log.warning("dropping job %s: simulation expired or unknown persona", job["job_id"])
            return

        key = store.cache_key(persona, spec, prompt)
        cached = await self.redis.get(key)
        if cached is not None:
            await store.finish_persona(self.redis, sim_id, persona, result=cached, from_cache=True)
            return

        try:
            output = await asyncio.wait_for(
                self.run_persona(persona, prompt), timeout=config.JOB_TIMEOUT
            )
        except Exception as exc:
            await self._retry_or_fail(job, exc)
            return

        result = json.dumps(output)
        await self.redis.set(key, result, ex=config.PERSONA_CACHE_TTL)
        await store.finish_persona(self.redis, sim_id, persona, result=result)

    async def _retry_or_fail(self, job: Dict[str, Any], exc: BaseException) -> None:
        attempt = job["attempt"] + 1
        error = f"{type(exc).__name__}: {exc}"
        if attempt < config.JOB_MAX_ATTEMPTS and _is_retryable(exc):
            log.warning("job %s (%s) attempt %d failed, retrying: %s",
                        job["job_id"], job["persona"], attempt, error)
            await asyncio.sleep(min(config.RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1), 30))
            await self.redis.lpush(store.QUEUE, store.make_job(job["sim_id"], job["persona"], attempt))
        else:
            log.error("job %s (%s) failed permanently: %s", job["job_id"], job["persona"], error)
            await store.finish_persona(self.redis, job["sim_id"], job["persona"], error=error)

    async def _heartbeat_once(self) -> None:
        pipe = self.redis.pipeline(transaction=True)
        pipe.set(store.heartbeat_key(self.id), "1", ex=config.HEARTBEAT_TTL)
        pipe.sadd(store.WORKERS, self.id)
        await pipe.execute()

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(config.HEARTBEAT_INTERVAL)
            try:
                await self._heartbeat_once()
            except Exception:
                log.exception("heartbeat failed")

    async def _reap_loop(self) -> None:
        while True:
            try:
                await self.reap_dead_workers()
            except Exception:
                log.exception("reaper failed")
            await asyncio.sleep(config.REAP_INTERVAL)

    async def reap_dead_workers(self) -> int:
        recovered = 0
        for wid in await self.redis.smembers(store.WORKERS):
            if wid == self.id or await self.redis.exists(store.heartbeat_key(wid)):
                continue
            moved = await self._requeue_from(wid)
            await self.redis.srem(store.WORKERS, wid)
            if moved:
                log.warning("requeued %d jobs from dead worker %s", moved, wid)
            recovered += moved
        return recovered

    async def _requeue_from(self, worker_id: str) -> int:
        moved = 0
        # Back onto the consuming end, so recovered jobs run next.
        while await self.redis.lmove(store.processing_key(worker_id), store.QUEUE, "RIGHT", "RIGHT"):
            moved += 1
        return moved


async def _serve(concurrency: int) -> None:
    from .personas import persona_specs, run_persona

    redis = Redis.from_url(config.REDIS_URL, decode_responses=True)
    worker = Worker(redis, persona_specs(), run_persona, concurrency)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)
    try:
        await worker.run()
    finally:
        await redis.aclose()


def _process_main(concurrency: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(process)d %(levelname)s %(message)s")
    asyncio.run(_serve(concurrency))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-p", "--processes", type=int, default=config.WORKER_PROCESSES)
    parser.add_argument("-c", "--concurrency", type=int, default=config.WORKER_CONCURRENCY)
    args = parser.parse_args()

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    # Without credentials every job would burn its retries on the same error.
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() not in ("1", "true"):
        parser.exit(1, "GOOGLE_API_KEY is not set (or set GOOGLE_GENAI_USE_VERTEXAI=true)\n")

    if args.processes <= 1:
        _process_main(args.concurrency)
        return

    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_process_main, args=(args.concurrency,)) for _ in range(args.processes)]
    for proc in procs:
        proc.start()

    def forward(signum, _frame):
        for proc in procs:
            if proc.is_alive():
                os.kill(proc.pid, signum)

    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGTERM, forward)
    for proc in procs:
        proc.join()


if __name__ == "__main__":
    main()
