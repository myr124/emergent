"""Redis layout for simulations, persona jobs and the persona response cache.

A simulation fans out into one job per persona. Each job is a JSON blob on
QUEUE; workers move it atomically onto their own processing list while they
run it, so a crashed worker's jobs can be put back on the queue.
"""

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from redis.asyncio import Redis

from . import config

PREFIX = "emergent"
QUEUE = f"{PREFIX}:queue"
WORKERS = f"{PREFIX}:workers"

RUNNING = "running"
FINISHED_STATUSES = ("completed", "partial", "failed")


def processing_key(worker_id: str) -> str:
    return f"{PREFIX}:processing:{worker_id}"


def heartbeat_key(worker_id: str) -> str:
    return f"{PREFIX}:worker:{worker_id}:heartbeat"


def sim_key(sim_id: str) -> str:
    return f"{PREFIX}:sim:{sim_id}"


def prompt_key(sim_id: str) -> str:
    return f"{PREFIX}:sim:{sim_id}:prompt"


def results_key(sim_id: str) -> str:
    return f"{PREFIX}:sim:{sim_id}:results"


def errors_key(sim_id: str) -> str:
    return f"{PREFIX}:sim:{sim_id}:errors"


def inflight_key(prompt_hash: str) -> str:
    return f"{PREFIX}:inflight:{prompt_hash}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cache_key(persona: str, spec: Dict[str, str], prompt: str) -> str:
    """Same persona slot + same model + same instructions + same plan = same answer.

    The persona name is part of the key on purpose: personas of one archetype
    share an instruction, and keying on the instruction alone would collapse
    them all into one cached response.
    """
    material = json.dumps(
        [config.CACHE_VERSION, persona, spec["model"], spec["instruction"], prompt]
    )
    return f"{PREFIX}:persona-cache:{_sha256(material)}"


def make_job(sim_id: str, persona: str, attempt: int = 0) -> str:
    return json.dumps(
        {"job_id": uuid.uuid4().hex, "sim_id": sim_id, "persona": persona, "attempt": attempt}
    )


async def create_simulation(
    r: Redis, prompt: str, specs: Dict[str, Dict[str, str]]
) -> Tuple[str, bool]:
    """Create a simulation and enqueue its uncached personas.

    Returns (sim_id, deduplicated). An identical plan that is still running
    returns the existing simulation instead of starting a second one.
    """
    prompt_hash = _sha256(prompt)
    sim_id = uuid.uuid4().hex

    if not await r.set(inflight_key(prompt_hash), sim_id, nx=True, ex=config.SIM_RESULT_TTL):
        existing = await r.get(inflight_key(prompt_hash))
        if existing and await r.hget(sim_key(existing), "status") == RUNNING:
            return existing, True
        await r.set(inflight_key(prompt_hash), sim_id, ex=config.SIM_RESULT_TTL)

    personas = list(specs)
    cached = await r.mget([cache_key(p, specs[p], prompt) for p in personas])
    hits = {p: c for p, c in zip(personas, cached) if c is not None}
    misses = [p for p in personas if p not in hits]

    now = str(time.time())
    status = RUNNING if misses else "completed"
    ttl = config.SIM_RESULT_TTL

    pipe = r.pipeline(transaction=True)
    fields = {
        "status": status,
        "total": len(personas),
        "completed": len(hits),
        "failed": 0,
        "cache_hits": len(hits),
        "prompt_hash": prompt_hash,
        "created_at": now,
    }
    if not misses:
        fields["finished_at"] = now
    pipe.hset(sim_key(sim_id), mapping=fields)
    pipe.expire(sim_key(sim_id), ttl)
    pipe.set(prompt_key(sim_id), prompt, ex=ttl)
    if hits:
        pipe.hset(results_key(sim_id), mapping=hits)
        pipe.expire(results_key(sim_id), ttl)
    if misses:
        pipe.lpush(QUEUE, *[make_job(sim_id, p) for p in misses])
    else:
        pipe.delete(inflight_key(prompt_hash))
    await pipe.execute()

    return sim_id, False


# Records one persona's outcome exactly once and finalizes the simulation when
# the last persona lands. Running it as a script keeps a redelivered job (after
# a worker crash) from being counted twice.
_FINISH_PERSONA = """
if redis.call('EXISTS', KEYS[1]) == 0 then return -1 end
if redis.call('HEXISTS', KEYS[2], ARGV[1]) == 1 or redis.call('HEXISTS', KEYS[3], ARGV[1]) == 1 then
  return 0
end
local counter = 'completed'
if ARGV[3] == 'ok' then
  redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
  redis.call('EXPIRE', KEYS[2], ARGV[5])
else
  redis.call('HSET', KEYS[3], ARGV[1], ARGV[2])
  redis.call('EXPIRE', KEYS[3], ARGV[5])
  counter = 'failed'
end
redis.call('HINCRBY', KEYS[1], counter, 1)
if ARGV[7] == '1' then redis.call('HINCRBY', KEYS[1], 'cache_hits', 1) end
local completed = tonumber(redis.call('HGET', KEYS[1], 'completed'))
local failed = tonumber(redis.call('HGET', KEYS[1], 'failed'))
local total = tonumber(redis.call('HGET', KEYS[1], 'total'))
if completed + failed >= total then
  local status = 'completed'
  if failed > 0 then
    if completed > 0 then status = 'partial' else status = 'failed' end
  end
  redis.call('HSET', KEYS[1], 'status', status, 'finished_at', ARGV[4])
  if redis.call('GET', KEYS[4]) == ARGV[6] then redis.call('DEL', KEYS[4]) end
end
return 1
"""


async def finish_persona(
    r: Redis,
    sim_id: str,
    persona: str,
    *,
    result: Optional[str] = None,
    error: Optional[str] = None,
    from_cache: bool = False,
) -> int:
    """Returns 1 if recorded, 0 if this persona was already recorded, -1 if the sim expired."""
    prompt_hash = await r.hget(sim_key(sim_id), "prompt_hash") or ""
    outcome = "ok" if error is None else "failed"
    return await r.eval(
        _FINISH_PERSONA,
        4,
        sim_key(sim_id),
        results_key(sim_id),
        errors_key(sim_id),
        inflight_key(prompt_hash),
        persona,
        result if error is None else error,
        outcome,
        str(time.time()),
        config.SIM_RESULT_TTL,
        sim_id,
        "1" if from_cache else "0",
    )


async def get_simulation(
    r: Redis, sim_id: str, specs: Dict[str, Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    meta = await r.hgetall(sim_key(sim_id))
    if not meta:
        return None

    created = float(meta["created_at"])
    finished = float(meta["finished_at"]) if meta.get("finished_at") else None
    body: Dict[str, Any] = {
        "sim_id": sim_id,
        "status": meta["status"],
        "total": int(meta["total"]),
        "completed": int(meta["completed"]),
        "failed": int(meta["failed"]),
        "cache_hits": int(meta["cache_hits"]),
        "elapsed_seconds": round((finished or time.time()) - created, 2),
    }

    if meta["status"] in FINISHED_STATUSES:
        results = await r.hgetall(results_key(sim_id))
        # Keyed by each agent's output_key, the same shape ADK sessions use,
        # so the frontend's existing transformer reads it unchanged.
        state = {
            specs[p]["output_key"] if p in specs else p: json.loads(v)
            for p, v in results.items()
        }
        body["list_sessions"] = [{"id": sim_id, "appName": "multi-persona-agent", "state": state}]
        body["errors"] = await r.hgetall(errors_key(sim_id))

    return body


async def queue_stats(r: Redis) -> Dict[str, Any]:
    worker_ids: List[str] = list(await r.smembers(WORKERS))
    pipe = r.pipeline(transaction=False)
    pipe.llen(QUEUE)
    for wid in worker_ids:
        pipe.exists(heartbeat_key(wid))
        pipe.llen(processing_key(wid))
    replies = await pipe.execute()

    queued, rest = replies[0], replies[1:]
    alive = [wid for i, wid in enumerate(worker_ids) if rest[2 * i]]
    in_progress = sum(rest[2 * i + 1] for i in range(len(worker_ids)))
    return {"queued": queued, "in_progress": in_progress, "workers_alive": len(alive)}
