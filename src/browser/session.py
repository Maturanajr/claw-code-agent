"""
BrowserSession — singleton Playwright browser with stealth + persistent cache.

Uses async Playwright in a dedicated background thread with its own ProactorEventLoop
(required on Windows for asyncio subprocess support).
"""
from __future__ import annotations

import asyncio
import random
import sys
import threading
from concurrent.futures import Future
from typing import Any, Optional

from .config import BrowserConfig

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
const _origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) =>
  p.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : _origQuery(p);
"""


class _BrowserLoop:
    """
    Dedicated asyncio event loop running in a daemon thread.
    On Windows, uses ProactorEventLoop (required for subprocess support).
    The loop is created INSIDE the thread to avoid cross-thread issues.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="browser-loop")
        self._thread.start()
        self._ready.wait(timeout=10)

    def _run(self) -> None:
        if sys.platform == "win32":
            self._loop = asyncio.ProactorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def run(self, coro) -> Any:
        fut: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=120)

    def stop(self) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)


class BrowserSession:
    """Thread-safe singleton browser session backed by a dedicated event loop."""

    _instance: Optional["BrowserSession"] = None
    _loop_instance: Optional[_BrowserLoop] = None
    _lock = threading.Lock()

    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self._playwright = None
        self._context = None
        self._page = None
        self._user_agent = random.choice(_USER_AGENTS)
        self._loop: _BrowserLoop = self._get_loop()

    @classmethod
    def _get_loop(cls) -> _BrowserLoop:
        if cls._loop_instance is None:
            cls._loop_instance = _BrowserLoop()
        return cls._loop_instance

    @classmethod
    def get(cls) -> Optional["BrowserSession"]:
        return cls._instance

    @classmethod
    def launch(cls, config: BrowserConfig) -> "BrowserSession":
        with cls._lock:
            if cls._instance and cls._instance.is_alive():
                return cls._instance
            session = cls(config)
            session._loop.run(session._async_start())
            cls._instance = session
            return session

    @classmethod
    def close_global(cls) -> str:
        with cls._lock:
            if cls._instance:
                try:
                    cls._instance._loop.run(cls._instance._async_stop())
                except Exception:
                    pass
                cls._instance = None
                return "Browser closed."
            return "No browser was open."

    async def _async_start(self) -> None:
        from playwright.async_api import async_playwright
        cfg = self.config
        cfg.user_data_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        ua = self._user_agent if cfg.randomise_user_agent else _USER_AGENTS[0]

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(cfg.user_data_dir),
            headless=cfg.headless,
            slow_mo=cfg.slow_mo,
            viewport={"width": cfg.viewport_width, "height": cfg.viewport_height},
            user_agent=ua,
            locale=cfg.locale,
            timezone_id=cfg.timezone,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ],
            ignore_default_args=["--enable-automation"],
        )
        await self._context.add_init_script(_STEALTH_SCRIPT)
        self._context.set_default_timeout(cfg.default_timeout)
        self._context.set_default_navigation_timeout(cfg.navigation_timeout)

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

    async def _async_stop(self) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._page = None
        self._playwright = None

    def run(self, coro) -> Any:
        return self._loop.run(coro)

    def is_alive(self) -> bool:
        try:
            if self._page is None:
                return False
            return self._loop.run(self._async_is_alive())
        except Exception:
            return False

    async def _async_is_alive(self) -> bool:
        try:
            return not self._page.is_closed()
        except Exception:
            return False

    def status(self) -> dict:
        if not self.is_alive():
            return {"alive": False, "url": None, "title": None}
        try:
            return self._loop.run(self._async_status())
        except Exception as e:
            return {"alive": False, "error": str(e)}

    async def _async_status(self) -> dict:
        return {
            "alive": True,
            "url": self._page.url,
            "title": await self._page.title(),
            "headless": self.config.headless,
            "user_agent": self._user_agent,
        }
