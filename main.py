"""
FastAPI wrapper that delegates core ADK endpoints to google.adk's helper.

This file uses `get_fast_api_app` from `google.adk.cli.fast_api` to register the
standard ADK endpoints (chat, stream, web UI, etc.) for the agent folder
`multi-persona-agent`. It also exposes a small `/health` endpoint and a helper
`/agent-info` endpoint that reads the `root_agent` symbol from the agent module
so you can inspect basic metadata.
"""

from typing import Any, Dict, Optional
import os
import json
import sys
import types
from importlib.machinery import SourceFileLoader

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import asyncio

# ADK helper to register the built-in ADK endpoints
from google.adk.cli.fast_api import get_fast_api_app

# Compute paths relative to this file
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
AGENT_DIR = os.path.abspath(os.path.join(BASE_DIR, "multi-persona-agent"))
AGENT_PY_PATH = os.path.join(AGENT_DIR, "agent.py")

# Load env for the agent (e.g., GOOGLE_API_KEY)
load_dotenv(os.path.join(AGENT_DIR, ".env"))

# Simple SQLite-backed session DB (dev)
SESSION_DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "sessions.db"))
SESSION_DB_URL = f"sqlite:///{SESSION_DB_PATH}"

# Delegate to ADK's fast API builder. It will register endpoints like /chat, /stream,
# and the ADK web UI if `web=True`.
app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_db_kwargs={"url": SESSION_DB_URL},
    allow_origins=["*"],  # TODO: tighten in production
    web=True,
)

# Disable OpenAPI/docs generation to avoid Pydantic schema issues during startup.
# This prevents FastAPI from trying to build the OpenAPI schema (which inspects
# ADK types that Pydantic cannot generate schemas for in this environment).
# The ADK endpoints will still be registered by get_fast_api_app.
# app.openapi = lambda: None
# app.docs_url = None
# app.redoc_url = None
# app.openapi_url = None

# Add any additional middleware you want
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_root_agent_from_agent_py(agent_py_path: str):
    """
    Load the project's agent.py and return `root_agent`.

    This sets up a temporary package entry so relative imports inside agent.py
    (e.g. `from .utils import ...`) resolve when we load the module by path.
    """
    if not os.path.exists(agent_py_path):
        raise FileNotFoundError(f"agent.py not found at: {agent_py_path}")

    agent_dir = os.path.dirname(agent_py_path)
    package_name = "mp_agent_pkg"

    # Ensure package entry with proper __path__ so relative imports work
    pkg = types.ModuleType(package_name)
    pkg.__path__ = [agent_dir]
    sys.modules[package_name] = pkg

    loader = SourceFileLoader(f"{package_name}.agent", agent_py_path)
    module = types.ModuleType(loader.name)
    module.__package__ = package_name
    loader.exec_module(module)  # type: ignore
    sys.modules[loader.name] = module

    if not hasattr(module, "root_agent"):
        raise AttributeError("agent.py does not expose `root_agent`")
    return getattr(module, "root_agent")


@app.get("/health")
async def health_check():
    """Simple health check for the service."""
    return {"status": "healthy"}


@app.get("/agent-info")
async def agent_info():
    """Return basic metadata for the loaded root_agent."""
    try:
        root_agent = _load_root_agent_from_agent_py(AGENT_PY_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load root_agent: {e}")

    info: Dict[str, Any] = {
        "agent_name": getattr(root_agent, "name", None),
        "description": getattr(root_agent, "description", None),
        "model": getattr(root_agent, "model", None),
    }

    tools = []
    try:
        for t in getattr(root_agent, "tools", []) or []:
            tools.append(getattr(t, "__name__", str(t)))
    except Exception:
        tools = [str(getattr(root_agent, "tools", None))]

    info["tools"] = tools
    return info


class SimpleChatRequest(BaseModel):
    input: str
    user_id: str = "anonymous"
    session_id: Optional[str] = None
    app_name: Optional[str] = None
    # Optional emergency_plan payload (string or structured JSON). If the caller
    # provides structured JSON (object/array), we'll serialize it to a JSON string
    # and set the EMERGENCY_PHASES environment variable so the agents can consume it.
    emergency_plan: Optional[Any] = None


async def get_first_app_name() -> str:
    """Query the ADK helper to pick the first registered app name."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("http://127.0.0.1:8080/list-apps", timeout=5.0)
            j = r.json()
            return j[0] if isinstance(j, list) and j else "prompts"
    except Exception:
        return "prompts"


@app.post("/chat")
async def chat_simple(req: SimpleChatRequest):
    """
    Simple chat wrapper: translates {input, user_id, session_id, app_name}
    into the ADK /run payload and forwards it to the internal /run endpoint.
    """
    app_name = req.app_name or await get_first_app_name()

    # If the caller provided an emergency plan in this request, expose it to the
    # agents by writing it to the process environment. The ADK agent loader
    # re-imports agent modules on each run, so setting this env var before
    # forwarding to /run lets multi-persona-agent/agent.py read the user-provided
    # emergency plan via os.environ["EMERGENCY_PHASES"].
    if getattr(req, "emergency_plan", None):
        plan = req.emergency_plan
        # If the caller passed structured JSON (dict/list), serialize it to a string.
        # If they passed a raw string, use it directly.
        os.environ["EMERGENCY_PHASES"] = (
            json.dumps(plan) if not isinstance(plan, str) else plan
        )

    # Ensure a valid session exists. If the caller didn't provide a session_id,
    # create one via the ADK session-create endpoint: POST /apps/{app_name}/users/{user_id}/sessions
    session_id = req.session_id
    if not session_id:
        try:
            async with httpx.AsyncClient() as client:
                create_resp = await client.post(
                    f"http://127.0.0.1:8080/apps/{app_name}/users/{req.user_id}/sessions",
                    json={},
                    timeout=10.0,
                )
                create_json = create_resp.json()
                # Try common keys for returned session id
                session_id = (
                    create_json.get("session_id")
                    or create_json.get("sessionId")
                    or create_json.get("id")
                    or create_json.get("session", {}).get("id")
                    or "default"
                )
        except Exception:
            session_id = "default"

    run_payload = {
        "app_name": app_name,
        "user_id": req.user_id,
        "session_id": session_id,
        "new_message": {"role": "user", "parts": [{"text": req.input}]},
        "streaming": False,
    }

    # Forward request to the ADK /run endpoint using an async HTTP client.
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://127.0.0.1:8080/run", json=run_payload, timeout=30.0
            )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to call internal /run: {e}"
        )

    # Mirror the /run response (list of events) or return an error body
    try:
        return resp.json()
    except Exception:
        return {"status": "error", "detail": resp.text}


if __name__ == "__main__":
    # Run locally for development:
    # uvicorn server.main:app --reload --port 8080
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
