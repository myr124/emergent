"""
Compatibility shim that loads the parent `multi-persona-agent/agent.py` by file path
and re-exports its `root_agent`. This uses SourceFileLoader and sets up a temporary
package with __path__ pointing to the parent directory so relative imports inside
agent.py (e.g. `from .utils import ...`) resolve correctly.
"""

import os
import sys
import types
from importlib.machinery import SourceFileLoader

# Resolve paths
this_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(this_dir)
agent_py_path = os.path.join(parent_dir, "agent.py")

if not os.path.exists(agent_py_path):
    raise FileNotFoundError(f"agent.py not found at: {agent_py_path}")

# Create a temporary package so relative imports in agent.py work.
package_name = "mp_agent_pkg_for_prompts"
pkg = types.ModuleType(package_name)
pkg.__path__ = [parent_dir]
sys.modules[package_name] = pkg

# Load the agent.py module under the temporary package namespace.
loader = SourceFileLoader(f"{package_name}.agent", agent_py_path)
module = types.ModuleType(loader.name)
module.__package__ = package_name
loader.exec_module(module)  # type: ignore
sys.modules[loader.name] = module

if not hasattr(module, "root_agent"):
    raise AttributeError("Loaded agent.py does not expose `root_agent`")

# Re-export root_agent so the ADK loader can find it at prompts.agent.root_agent
root_agent = getattr(module, "root_agent")
