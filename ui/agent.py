from __future__ import annotations

import traceback
from pathlib import Path

from src.agent_runtime import LocalCodingAgent
from src.agent_types import AgentRuntimeConfig, AgentPermissions, ModelConfig, ModelPricing
from src.session_store import load_agent_session
from src.browser.registry import browser_tool_registry
from src.browser.prompts import get_browser_guidance_section

# shared result holder between main thread and worker thread
result_holder: dict = {}


def build_agent(cfg: dict) -> LocalCodingAgent:
    from src.agent_tools import default_tool_registry
    from src.web_search import WEB_SEARCH_TOOL, WEB_FETCH_TOOL

    # base registry + web search (always available)
    registry = {**default_tool_registry(), WEB_SEARCH_TOOL.name: WEB_SEARCH_TOOL, WEB_FETCH_TOOL.name: WEB_FETCH_TOOL}

    # merge browser tools if enabled
    if cfg.get("browser_enabled", False):
        registry = {**registry, **browser_tool_registry()}

    # web search guidance always injected
    web_prompt = (
        "## Web Search\n"
        "You have `web_search` and `web_fetch` tools for looking up information online.\n"
        "- Use `web_search` whenever you need current information, facts, or to research a topic.\n"
        "- Use `web_fetch` to read a specific URL as plain text.\n"
        "- These are pure HTTP requests — fast, cheap, no browser needed.\n"
        "- ALWAYS prefer `web_search` over the browser for information lookup.\n"
        "- Only use the browser when you need to interact with a page (click, scroll, fill forms).\n"
        "- NEVER fabricate information — if unsure, use `web_search` first."
    )

    # browser guidance injected as append_system_prompt
    browser_prompt = get_browser_guidance_section(cfg.get("browser_enabled", False))
    combined_prompt = web_prompt + ("\n\n" + browser_prompt if browser_prompt else "")

    return LocalCodingAgent(
        model_config=ModelConfig(
            model=cfg["model"],
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            pricing=ModelPricing(
                input_cost_per_million_tokens_usd=cfg.get("input_cost_per_million", 0.0),
                output_cost_per_million_tokens_usd=cfg.get("output_cost_per_million", 0.0),
            ),
        ),
        runtime_config=AgentRuntimeConfig(
            cwd=Path(cfg["cwd"]).resolve(),
            max_turns=cfg["max_turns"],
            permissions=AgentPermissions(
                allow_file_write=cfg["allow_write"],
                allow_shell_commands=cfg["allow_shell"],
                allow_destructive_shell_commands=cfg["unsafe"],
            ),
        ),
        tool_registry=registry,
        append_system_prompt=combined_prompt,
    )


def run_agent(prompt: str, session_id: str | None, cfg: dict) -> None:
    """Worker function — runs in a background thread."""
    try:
        # restore browser URL if resuming a session
        if session_id and cfg.get("browser_enabled", False):
            _restore_browser_if_needed(session_id, cfg)

        agent = build_agent(cfg)
        if session_id:
            stored = load_agent_session(
                session_id,
                directory=Path(".port_sessions/agent").resolve(),
            )
            result = agent.resume(prompt, stored)
        else:
            result = agent.run(prompt)

        # save browser URL after run
        if cfg.get("browser_enabled", False):
            _save_browser_url(result.session_id)

        result_holder["result"] = result
        result_holder["error"] = None
        result_holder["tb"] = None
    except Exception as exc:
        result_holder["result"] = None
        result_holder["error"] = str(exc)
        result_holder["tb"] = traceback.format_exc()


def _save_browser_url(session_id: str | None) -> None:
    """Persist current browser URL after a run."""
    try:
        from src.browser.session import BrowserSession
        from src.browser.knowledge import save_browser_state
        s = BrowserSession.get()
        if s and s.is_alive():
            url = s._page.url
            if url and url not in ("about:blank", ""):
                save_browser_state(url, session_id)
    except Exception:
        pass


def _restore_browser_if_needed(session_id: str, cfg: dict) -> None:
    """If browser is open and we have a saved URL for this session, navigate back."""
    try:
        from src.browser.session import BrowserSession, BrowserConfig
        from src.browser.knowledge import load_browser_state

        state = load_browser_state()
        if not state.get("url") or state.get("session_id") != session_id:
            return

        url = state["url"]
        if url in ("about:blank", ""):
            return

        # ensure browser is open
        s = BrowserSession.get()
        if s is None or not s.is_alive():
            s = BrowserSession.launch(BrowserConfig(
                headless=cfg.get("browser_headless", False)
            ))

        # only navigate if not already on that URL
        current = s._page.url
        if current != url:
            s.run(s._page.goto(url, wait_until="domcontentloaded"))
    except Exception:
        pass


def cfg_from_state(state, input_cost: float = 0.0, output_cost: float = 0.0) -> dict:
    """Snapshot relevant keys from st.session_state (safe for threads)."""
    return {
        **{k: state[k] for k in ("model", "base_url", "api_key", "cwd", "max_turns",
                                  "allow_write", "allow_shell", "unsafe")},
        "input_cost_per_million":  input_cost,
        "output_cost_per_million": output_cost,
        "browser_enabled":  state.get("browser_enabled", False),
        "browser_headless": state.get("browser_headless", False),
    }
