import os
from typing import Any


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
