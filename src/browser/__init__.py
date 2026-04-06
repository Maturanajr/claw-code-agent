"""Browser plugin for Claw Code Agent — Playwright-based stealth browser."""
from .registry import browser_tool_registry
from .session import BrowserSession
from .config import BrowserConfig

__all__ = ["browser_tool_registry", "BrowserSession", "BrowserConfig"]
