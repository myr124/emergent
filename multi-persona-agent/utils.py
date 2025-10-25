import os
import json
from typing import Any, Dict, List


def load_text(path: str) -> str:
    """
    Generic function to load text from a file.

    Args:
        path: Absolute or relative path to the file. If relative, resolved from package directory.

    Returns:
        File contents as a string.

    Raises:
        FileNotFoundError if the file does not exist.
        OSError for other IO errors.
    """
    base_dir = os.path.dirname(__file__)

    # If absolute path, use as-is; otherwise resolve relative to package dir
    if os.path.isabs(path):
        full_path = path
    else:
        full_path = os.path.normpath(os.path.join(base_dir, path))

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"File not found: {full_path}")

    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def load_instructions(path: str) -> str:
    """
    Load instruction text for agents.

    Behavior:
    - If `path` starts with "multi-persona-agent/", the remainder is resolved
      relative to this package directory (where this utils.py lives).
    - Otherwise `path` is treated as relative to this package directory.
    - Returns the file contents as a string.

    Raises:
    - FileNotFoundError if the file does not exist.
    - OSError for other IO errors.
    """
    base_dir = os.path.dirname(__file__)
    prefix = "multi-persona-agent/"
    if path.startswith(prefix):
        rel_path = path[len(prefix) :]
    else:
        rel_path = path

    full_path = os.path.normpath(os.path.join(base_dir, rel_path))

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Instruction file not found: {full_path}")

    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def load_emergency_plan_phases() -> List[Dict[str, Any]]:
    """
    Load emergency plan phases from the emergency_plan.txt JSON file.

    Returns:
    - List of phase dictionaries with period info, injects, and eocActions

    Raises:
    - FileNotFoundError if emergency_plan.txt does not exist.
    - json.JSONDecodeError if the file is not valid JSON.
    """
    base_dir = os.path.dirname(__file__)
    plan_path = os.path.normpath(os.path.join(base_dir, "prompts", "emergency_plan.txt"))

    if not os.path.exists(plan_path):
        raise FileNotFoundError(f"Emergency plan file not found: {plan_path}")

    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)

    return plan_data.get("actionPlan", {}).get("periods", [])


def format_phases_for_prompt() -> str:
    """
    Format emergency plan phases into a readable string for LLM prompts.

    Returns:
    - Formatted string describing each phase with key events and actions
    """
    phases = load_emergency_plan_phases()
    formatted = []

    for period in phases:
        period_num = period.get("periodNumber")
        start_time = period.get("startTime")
        end_time = period.get("endTime")
        phase_type = period.get("phase")

        formatted.append(f"\n=== PHASE {period_num} ({start_time} to {end_time}) - {phase_type.upper()} ===")

        # Add injects (events)
        injects = period.get("injects", [])
        if injects:
            formatted.append("\nKey Events:")
            for inject in injects:
                formatted.append(f"  - {inject.get('title')}: {inject.get('description')}")

        # Add EOC actions
        eoc_actions = period.get("eocActions", [])
        if eoc_actions:
            formatted.append("\nOfficial Actions:")
            for action in eoc_actions:
                formatted.append(f"  - {action.get('actionType')}: {action.get('details')}")

    return "\n".join(formatted)


def load_archetypes() -> Dict[str, str]:
    """
    Load personality archetypes from the archetypes.json file.

    Returns:
    - Dictionary mapping archetype names to their descriptions

    Raises:
    - FileNotFoundError if archetypes.json does not exist.
    - json.JSONDecodeError if the file is not valid JSON.
    """
    base_dir = os.path.dirname(__file__)
    archetypes_path = os.path.normpath(os.path.join(base_dir, "prompts", "archetypes.json"))

    if not os.path.exists(archetypes_path):
        raise FileNotFoundError(f"Archetypes file not found: {archetypes_path}")

    with open(archetypes_path, "r", encoding="utf-8") as f:
        archetypes = json.load(f)

    return archetypes
