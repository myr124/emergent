"""Loads the persona definitions from multi-persona-agent and runs one persona."""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

AGENT_PKG_DIR = Path(__file__).resolve().parent.parent / "multi-persona-agent"
_MODULE_NAME = "multi_persona_agent"


def _agent_module():
    # The agent folder has a hyphen in its name, so it can't be imported normally.
    if _MODULE_NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _MODULE_NAME,
            AGENT_PKG_DIR / "__init__.py",
            submodule_search_locations=[str(AGENT_PKG_DIR)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[_MODULE_NAME] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{_MODULE_NAME}.agent")


def persona_specs() -> Dict[str, Dict[str, str]]:
    return _agent_module().PERSONA_SPECS


async def run_persona(name: str, prompt: str) -> Dict[str, Any]:
    """Run a single persona agent against the plan and return its validated output."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent_module = _agent_module()
    runner = InMemoryRunner(
        agent=agent_module.build_persona_agent(name), app_name="emergent-worker"
    )
    session = await runner.session_service.create_session(
        app_name="emergent-worker", user_id="worker"
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    text = None
    async for event in runner.run_async(
        user_id="worker", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(part.text or "" for part in event.content.parts)

    if not text:
        raise RuntimeError(f"persona {name} produced no final response")
    return agent_module.PersonaDetailedSchema.model_validate_json(text).model_dump()
