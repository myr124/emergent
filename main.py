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
from importlib.machinery import SourceFileLoader
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import asyncio

# ADK helper to register the built-in ADK endpoints
from google.adk.cli.fast_api import get_fast_api_app

# Compute paths relative to this file
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
AGENT_DIR = BASE_DIR  # Parent directory containing multi_tool_agent
AGENT_PY_PATH = os.path.join(AGENT_DIR, "multi-persona-agent")

# Load env for the agent (e.g., GOOGLE_API_KEY)
load_dotenv(os.path.join(AGENT_DIR, ".env"))

# Simple SQLite-backed session DB (dev)
SESSION_DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "sessions.db"))
SESSION_DB_URL = f"sqlite:///{SESSION_DB_PATH}"

# Delegate to ADK's fast API builder. It will register endpoints like /chat, /stream,
# and the ADK web UI if `web=True`.
app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_db_kwargs=SESSION_DB_URL,
    allow_origins=["*"],  # In production, restrict this
    web=True,  # Enable the ADK Web UI
)


@app.get("/health")
async def health_check():
    """Simple health check for the service."""
    return {"status": "healthy"}


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    app_name: str = Form("multi-persona-agent"),
    user_id: str = Form("user"),
    payload: str = Form(None),
):
    """
    Receive a multipart/form-data upload. 'file' contains the file contents.
    Optional form fields: app_name, user_id. Optional 'payload' can be a JSON string.
    """
    content = await file.read()
    # If payload JSON was provided as a form field, parse it
    parsed_payload = None
    if payload:
        try:
            parsed_payload = json.loads(payload)
        except Exception:
            parsed_payload = {"raw": payload}
    return {
        "filename": file.filename,
        "size": len(content),
        "app_name": app_name,
        "user_id": user_id,
        "payload": parsed_payload,
    }


# Pydantic model to accept JSON body for /simulate-flow.
# Using a model provides validation and automatic OpenAPI docs.
class SimulatePayload(BaseModel):
    app_name: Optional[str] = None
    user_id: Optional[str] = None
    # Optionally allow callers to provide the newMessage body used in /run_sse
    new_message: Optional[Dict[str, Any]] = None
    streaming: Optional[bool] = None
    # Any other overrides can be added here


@app.post("/simulate-flow")
async def simulate_flow(
    request: Request,
    payload: Optional[SimulatePayload] = None,
    file: UploadFile = File(None),
    form_app_name: Optional[str] = Form(None),
    form_user_id: Optional[str] = Form(None),
    form_payload: Optional[str] = Form(None),
    app_name: str = "multi-persona-agent",
    user_id: str = "user",
):
    """
    Simulate a request flow against the ADK endpoints registered by get_fast_api_app.

    Sequence:
      1) POST /apps/{app_name}/users/{user_id}/sessions
      2) GET  /apps/{app_name}/eval_sets
      3) GET  /apps/{app_name}/eval_results
      4) GET  /apps/{app_name}/users/{user_id}/sessions
      5) POST /run_sse

    This endpoint forwards the requests to the local service (using the same host/port
    the incoming request used) and prints INFO-style lines similar to the example flow.
    The JSON summary of responses is returned to the caller.

    Notes:
      - If you send a JSON body, it will be parsed into `payload` (Content-Type: application/json).
        Fields in that JSON (app_name, user_id, new_message, streaming) will override the
        corresponding query parameters.
      - You can still call this endpoint using query parameters (existing behavior).
      - This handler also accepts multipart/form-data (file + form fields). If a multipart
        request is received, form fields (form_app_name, form_user_id, form_payload) or a
        JSON file upload will be used to populate the same parameters.
    """
    # Support either JSON body (SimulatePayload) OR multipart/form-data with UploadFile/Form fields.
    # Priority:
    # 1) If multipart/form-data with file or form_payload is provided, use form values or parsed file content.
    # 2) Else if JSON body (payload) is provided, use payload fields.
    # 3) Else fall back to query params (app_name, user_id).
    parsed_form_payload = None

    if file is not None:
        # Prefer an explicit JSON form field if provided.
        if form_payload:
            try:
                parsed_form_payload = json.loads(form_payload)
            except Exception:
                parsed_form_payload = {"raw": form_payload}
        else:
            # Try to parse uploaded file contents as JSON (useful if the client uploaded a .json payload).
            try:
                content_bytes = await file.read()
                content_text = content_bytes.decode("utf-8")
                parsed = json.loads(content_text)
                if isinstance(parsed, dict):
                    parsed_form_payload = parsed
            except Exception:
                parsed_form_payload = None

        if parsed_form_payload:
            # Override app/user from parsed payload or explicit form fields
            app_name = parsed_form_payload.get("app_name", form_app_name or app_name)
            user_id = parsed_form_payload.get("user_id", form_user_id or user_id)
            payload = SimulatePayload(
                app_name=parsed_form_payload.get("app_name"),
                user_id=parsed_form_payload.get("user_id"),
                new_message=parsed_form_payload.get("new_message"),
                streaming=parsed_form_payload.get("streaming"),
            )
        else:
            # Use explicit form fields if present
            app_name = form_app_name or app_name
            user_id = form_user_id or user_id
    elif payload:
        app_name = payload.app_name or app_name
        user_id = payload.user_id or user_id

    base_url = str(request.base_url).rstrip("/")
    # Attempt to determine a port for the INFO log line; fall back to 0 if unknown.
    try:
        port_display = (
            request.client.port if request.client and request.client.port else 0
        )
    except Exception:
        port_display = 0

    async def _safe_json(resp: httpx.Response):
        try:
            return resp.json()
        except Exception:
            return {"text": resp.text}

    results = {}
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # 1) Create session
        try:
            resp = await client.post(
                f"/apps/{app_name}/users/{user_id}/sessions", json={}
            )
            print(
                f'INFO:     127.0.0.1:{port_display} - "POST /apps/{app_name}/users/{user_id}/sessions HTTP/1.1" {resp.status_code} OK'
            )
            results["create_session"] = await _safe_json(resp)
        except Exception as e:
            results["create_session_error"] = str(e)
            # continue but record error
            print(
                f"ERROR: failed POST /apps/{app_name}/users/{user_id}/sessions -> {e}"
            )
            results["status"] = "partial_failure"
            return results

        # Try to extract session id from common response shapes
        create_json = results.get("create_session") or {}
        session_id = (
            create_json.get("session_id")
            or create_json.get("sessionId")
            or create_json.get("id")
            or (create_json.get("session") or {}).get("id")
            or "default-session"
        )

        await asyncio.sleep(0.1)

        # 2) GET eval_sets
        try:
            resp = await client.get(f"/apps/{app_name}/eval_sets")
            print(
                f'INFO:     127.0.0.1:{port_display} - "GET /apps/{app_name}/eval_sets HTTP/1.1" {resp.status_code} OK'
            )
            results["eval_sets"] = await _safe_json(resp)
        except Exception as e:
            results["eval_sets_error"] = str(e)
            print(f"ERROR: failed GET /apps/{app_name}/eval_sets -> {e}")

        await asyncio.sleep(0.08)

        # 3) GET eval_results
        try:
            resp = await client.get(f"/apps/{app_name}/eval_results")
            print(
                f'INFO:     127.0.0.1:{port_display} - "GET /apps/{app_name}/eval_results HTTP/1.1" {resp.status_code} OK'
            )
            results["eval_results"] = await _safe_json(resp)
        except Exception as e:
            results["eval_results_error"] = str(e)
            print(f"ERROR: failed GET /apps/{app_name}/eval_results -> {e}")

        await asyncio.sleep(0.08)

        # 4) GET sessions list
        try:
            resp = await client.get(f"/apps/{app_name}/users/{user_id}/sessions")
            print(
                f'INFO:     127.0.0.1:{port_display} - "GET /apps/{app_name}/users/{user_id}/sessions HTTP/1.1" {resp.status_code} OK'
            )
            results["list_sessions"] = await _safe_json(resp)
        except Exception as e:
            results["list_sessions_error"] = str(e)
            print(f"ERROR: failed GET /apps/{app_name}/users/{user_id}/sessions -> {e}")

        await asyncio.sleep(0.08)

        # 5) POST /run_sse
        # Allow callers to override the newMessage via the JSON body (payload.new_message).
        default_new_message = {
            "parts": [{"text": "Hello from simulate_flow"}],
            "role": "user",
        }
        chosen_new_message = (
            payload.new_message
            if (payload and payload.new_message)
            else default_new_message
        )

        run_payload = {
            "appName": app_name,
            "userId": user_id,
            "sessionId": session_id,
            "newMessage": chosen_new_message,
            "streaming": payload.streaming
            if (payload and payload.streaming is not None)
            else False,
        }
        try:
            resp = await client.post("/run_sse", json=run_payload)
            print(
                f'INFO:     127.0.0.1:{port_display} - "POST /run_sse HTTP/1.1" {resp.status_code} OK'
            )
            results["run_sse"] = await _safe_json(resp)
        except Exception as e:
            results["run_sse_error"] = str(e)
            print(f"ERROR: failed POST /run_sse -> {e}")

    # Final status
    results.setdefault("status", "ok")
    return results


if __name__ == "__main__":
    print("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
