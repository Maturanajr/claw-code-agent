"""
Browser plugin — facade for src/browser/.
Enabled only when cfg["browser_enabled"] is True.
"""
from __future__ import annotations

from .base import ToolPlugin


def _enabled(cfg: dict) -> bool:
    return bool(cfg.get("browser_enabled", False))


def _build_plugin() -> ToolPlugin:
    from ..browser.registry import browser_tool_registry
    from ..browser.prompts import get_browser_guidance_section
    return ToolPlugin(
        name="browser",
        enabled=_enabled,
        tools=list(browser_tool_registry().values()),
        prompt=get_browser_guidance_section(browser_enabled=True),
    )


# lazy — only imported when the module is loaded by the discovery system
try:
    PLUGIN = _build_plugin()
except Exception as e:
    import warnings
    warnings.warn(f"[tools/browser] Failed to build browser plugin: {e}")
    # provide a disabled stub so discovery doesn't crash
    PLUGIN = ToolPlugin(name="browser", enabled=False, tools=[])
