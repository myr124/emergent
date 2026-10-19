"""Integration tests for the simulation queue. Needs a real Redis (REDIS_TEST_URL)."""

import asyncio
import json
import os
import time

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from simqueue import config, store
from simqueue.worker import Worker

REDIS_TEST_URL = os.getenv("REDIS_TEST_URL", "redis://localhost:6379/15")

SPECS = {
    f"{arch}_{i}": {
        "archetype": arch,
        "model": "fake-model",
        "instruction": f"you are {arch}",
        "output_key": f"{arch}_{i}_key",
    }
    for arch in ("lowincome", "retired", "student")
    for i in (1, 2, 3, 4)
}


@pytest.fixture
async def r():
    client = Redis.from_url(REDIS_TEST_URL, decode_responses=True)
    try:
        await client.ping()
    except RedisConnectionError:
        pytest.skip(f"no Redis at {REDIS_TEST_URL}")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture(autouse=True)
def fast_config(monkeypatch):
    monkeypatch.setattr(config, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(config, "HEARTBEAT_INTERVAL", 0.2)
    monkeypatch.setattr(config, "REAP_INTERVAL", 0.2)


class FakeAgents:
    """Stands in for the Gemini-backed persona run; tracks calls and concurrency."""

    def __init__(self, delay=0.05, fail_times=None):
        self.delay = delay
        self.fail_times = dict(fail_times or {})
        self.calls = []
        self.running = 0
        self.max_running = 0

    async def __call__(self, persona, prompt):
        self.calls.append(persona)
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.delay)
            if self.fail_times.get(persona, 0) > 0:
                self.fail_times[persona] -= 1
                raise RuntimeError("model overloaded")
            return {"race": "x", "age": 40, "sex": "f", "bio": f"{persona} / {prompt}",
                    "representation": 1.0, "response": []}
        finally:
            self.running -= 1


async def run_pool(r, agents, n_workers=2, concurrency=4):
    workers = [Worker(r, SPECS, agents, concurrency) for _ in range(n_workers)]
    tasks = [asyncio.create_task(w.run()) for w in workers]
    return workers, tasks


async def stop_pool(workers, tasks):
    for w in workers:
        w.stop()
    await asyncio.gather(*tasks)


async def wait_finished(r, sim_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sim = await store.get_simulation(r, sim_id, SPECS)
        if sim["status"] in store.FINISHED_STATUSES:
            return sim
        await asyncio.sleep(0.05)
    raise AssertionError(f"simulation still {sim['status']}: {sim}")


async def test_fans_out_one_job_per_persona_and_completes(r):
    agents = FakeAgents()
    sim_id, deduped = await store.create_simulation(r, "plan A", SPECS)
    assert not deduped
    assert await r.llen(store.QUEUE) == len(SPECS)

    workers, tasks = await run_pool(r, agents)
    sim = await wait_finished(r, sim_id)
    await stop_pool(workers, tasks)

    assert sim["status"] == "completed"
    assert sim["completed"] == len(SPECS) and sim["failed"] == 0
    state = sim["list_sessions"][0]["state"]
    assert set(state) == {s["output_key"] for s in SPECS.values()}
    assert state["retired_2_key"]["bio"] == "retired_2 / plan A"
    assert sorted(agents.calls) == sorted(SPECS)
    assert await r.llen(store.QUEUE) == 0


async def test_pool_runs_jobs_concurrently_within_limit(r):
    agents = FakeAgents(delay=0.2)
    sim_id, _ = await store.create_simulation(r, "plan A", SPECS)

    started = time.monotonic()
    workers, tasks = await run_pool(r, agents, n_workers=2, concurrency=3)
    await wait_finished(r, sim_id)
    elapsed = time.monotonic() - started
    await stop_pool(workers, tasks)

    assert agents.max_running == 6  # 2 workers x 3 consumers, never more
    assert elapsed < len(SPECS) * 0.2 / 2  # well under sequential time


async def test_repeated_plan_is_served_from_cache(r):
    agents = FakeAgents()
    workers, tasks = await run_pool(r, agents)
    first, _ = await store.create_simulation(r, "plan A", SPECS)
    await wait_finished(r, first)
    await stop_pool(workers, tasks)
    calls_after_first = len(agents.calls)

    second, deduped = await store.create_simulation(r, "plan A", SPECS)
    sim = await store.get_simulation(r, second, SPECS)

    assert not deduped and second != first
    assert sim["status"] == "completed"  # finished at submit time, no workers needed
    assert sim["cache_hits"] == len(SPECS)
    assert len(agents.calls) == calls_after_first
    assert await r.llen(store.QUEUE) == 0

    # Personas of the same archetype share an instruction but must not share a cache entry.
    state = sim["list_sessions"][0]["state"]
    assert state["lowincome_1_key"]["bio"] != state["lowincome_2_key"]["bio"]


async def test_changed_plan_misses_cache(r):
    agents = FakeAgents()
    workers, tasks = await run_pool(r, agents)
    await wait_finished(r, (await store.create_simulation(r, "plan A", SPECS))[0])
    sim = await wait_finished(r, (await store.create_simulation(r, "plan B", SPECS))[0])
    await stop_pool(workers, tasks)

    assert sim["cache_hits"] == 0
    assert len(agents.calls) == 2 * len(SPECS)


async def test_identical_plan_while_running_is_deduplicated(r):
    first, _ = await store.create_simulation(r, "plan A", SPECS)
    second, deduped = await store.create_simulation(r, "plan A", SPECS)

    assert deduped and second == first
    assert await r.llen(store.QUEUE) == len(SPECS)


async def test_transient_failure_is_retried(r):
    agents = FakeAgents(fail_times={"student_1": 1})
    sim_id, _ = await store.create_simulation(r, "plan A", SPECS)
    workers, tasks = await run_pool(r, agents)
    sim = await wait_finished(r, sim_id)
    await stop_pool(workers, tasks)

    assert sim["status"] == "completed"
    assert agents.calls.count("student_1") == 2


async def test_permanent_failure_marks_simulation_partial_and_is_not_cached(r, monkeypatch):
    monkeypatch.setattr(config, "JOB_MAX_ATTEMPTS", 2)
    agents = FakeAgents(fail_times={"student_1": 99})
    sim_id, _ = await store.create_simulation(r, "plan A", SPECS)
    workers, tasks = await run_pool(r, agents)
    sim = await wait_finished(r, sim_id)
    await stop_pool(workers, tasks)

    assert sim["status"] == "partial"
    assert sim["failed"] == 1 and sim["completed"] == len(SPECS) - 1
    assert "model overloaded" in sim["errors"]["student_1"]
    assert agents.calls.count("student_1") == 2

    rerun, _ = await store.create_simulation(r, "plan A", SPECS)
    rerun_sim = await store.get_simulation(r, rerun, SPECS)
    assert rerun_sim["cache_hits"] == len(SPECS) - 1
    assert json.loads(await r.lindex(store.QUEUE, 0))["persona"] == "student_1"


class ClientError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


async def test_client_errors_are_not_retried_but_rate_limits_are(r):
    attempts = {"student_1": 0, "student_2": 0}

    async def agents(persona, prompt):
        if persona in attempts:
            attempts[persona] += 1
            if persona == "student_1":
                raise ClientError(400)  # e.g. invalid API key
            if attempts[persona] == 1:
                raise ClientError(429)
        return {"bio": persona, "response": []}

    sim_id, _ = await store.create_simulation(r, "plan A", SPECS)
    workers, tasks = await run_pool(r, agents)
    sim = await wait_finished(r, sim_id)
    await stop_pool(workers, tasks)

    assert attempts == {"student_1": 1, "student_2": 2}
    assert sim["status"] == "partial" and list(sim["errors"]) == ["student_1"]


async def test_jobs_held_by_dead_worker_are_recovered(r):
    sim_id, _ = await store.create_simulation(r, "plan A", SPECS)
    # Simulate a worker that grabbed two jobs and then crashed (no heartbeat).
    dead = "dead-worker"
    await r.sadd(store.WORKERS, dead)
    for _ in range(2):
        await r.lmove(store.QUEUE, store.processing_key(dead), "RIGHT", "LEFT")

    agents = FakeAgents()
    workers, tasks = await run_pool(r, agents)
    sim = await wait_finished(r, sim_id)
    await stop_pool(workers, tasks)

    assert sim["status"] == "completed"
    assert await r.llen(store.processing_key(dead)) == 0
    assert not await r.sismember(store.WORKERS, dead)


async def test_redelivered_job_is_counted_once(r):
    sim_id, _ = await store.create_simulation(r, "plan A", SPECS)
    assert await store.finish_persona(r, sim_id, "student_1", result="{}") == 1
    assert await store.finish_persona(r, sim_id, "student_1", result="{}") == 0
    sim = await store.get_simulation(r, sim_id, SPECS)
    assert sim["completed"] == 1


async def test_queue_stats_reports_live_workers(r):
    await store.create_simulation(r, "plan A", SPECS)
    workers, tasks = await run_pool(r, FakeAgents(delay=1), n_workers=2, concurrency=2)
    await asyncio.sleep(0.3)
    stats = await store.queue_stats(r)
    await stop_pool(workers, tasks)

    assert stats["workers_alive"] == 2
    assert stats["in_progress"] == 4
    assert stats["queued"] == len(SPECS) - 4
