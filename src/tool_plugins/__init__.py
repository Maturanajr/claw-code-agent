"""
Auto-discovery for tool plugins in src/tool_plugins/.

NOTE: This is different from src/tools.py (porting inventory) and
src/tool_pool.py (porting pool) — those are part of the original
Claude Code porting architecture and should not be moved here.

This package contains EXECUTABLE tool plugins that extend the agent:
- Each file defines PLUGIN: ToolPlugin
- Discovered and registered automatically via extended_tool_registry()
- Add new tools by creating a new file with PLUGIN = ToolPlugin(...)

Any file in this directory that defines a module-level `PLUGIN: ToolPlugin`
is automatically discovered and registered.

Usage:
    from src.agent_tools import extended_tool_registry
    registry = extended_tool_registry(cfg)
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

from .base import ToolPlugin
from ..agent_tools import AgentTool

if TYPE_CHECKING:
    pass

_SKIP = {"__init__", "base"}


def _discover_plugins() -> list[tuple[str, object]]:
    """Import all modules in src/tools/ and return those that define PLUGIN."""
    plugins: list[tuple[str, object]] = []
    package_path = Path(__file__).parent
    for finder, module_name, _ in pkgutil.iter_modules([str(package_path)]):
        if module_name in _SKIP:
            continue
        try:
            mod = importlib.import_module(f".{module_name}", package=__name__)
            if hasattr(mod, "PLUGIN") and isinstance(mod.PLUGIN, ToolPlugin):
                plugins.append((module_name, mod.PLUGIN))
        except Exception as e:
            # never crash the agent because of a broken plugin
            import warnings
            warnings.warn(f"[tools] Failed to load plugin '{module_name}': {e}")
    return plugins


def load_plugins(cfg: dict) -> list[ToolPlugin]:
    """Return all enabled plugins for the given config."""
    return [
        plugin for _, plugin in _discover_plugins()
        if plugin.is_enabled(cfg)
    ]


def build_registry(cfg: dict) -> dict[str, AgentTool]:
    """Return a dict of all tools from enabled plugins."""
    registry: dict[str, AgentTool] = {}
    for plugin in load_plugins(cfg):
        for tool in plugin.tools:
            registry[tool.name] = tool
    return registry


def get_prompt_for_tool(tool_name: str, cfg: dict) -> str:
    """Return the plugin prompt for a specific tool name, or empty string."""
    for plugin in load_plugins(cfg):
        if tool_name in plugin.tool_names and plugin.prompt:
            return plugin.prompt
    return ""


def list_plugins(cfg: dict | None = None) -> list[str]:
    """Return names of all discovered (optionally filtered by enabled) plugins."""
    discovered = _discover_plugins()
    if cfg is None:
        return [name for name, _ in discovered]
    return [name for name, p in discovered if p.is_enabled(cfg)]
