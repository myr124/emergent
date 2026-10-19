"""HTTP routes for queued simulations."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis

from . import config, store
from .personas import persona_specs

router = APIRouter()
_redis = Redis.from_url(config.REDIS_URL, decode_responses=True)


class SimulationRequest(BaseModel):
    # The emergency plan the personas react to (sent to each persona as its input).
    prompt: str


@router.post("/simulations", status_code=202)
async def create_simulation(body: SimulationRequest):
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    if len(prompt.encode("utf-8")) > config.MAX_PROMPT_BYTES:
        raise HTTPException(status_code=413, detail="prompt is too large")

    specs = persona_specs()
    sim_id, deduplicated = await store.create_simulation(_redis, prompt, specs)
    status = await store.get_simulation(_redis, sim_id, specs)
    return {**status, "deduplicated": deduplicated}


@router.get("/simulations/{sim_id}")
async def get_simulation(sim_id: str):
    status = await store.get_simulation(_redis, sim_id, persona_specs())
    if status is None:
        raise HTTPException(status_code=404, detail="simulation not found or expired")
    return status


@router.get("/queue/stats")
async def queue_stats():
    return await store.queue_stats(_redis)
