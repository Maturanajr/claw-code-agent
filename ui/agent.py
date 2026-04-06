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

    # merge browser tools if enabled
    registry = default_tool_registry()
    if cfg.get("browser_enabled", False):
        registry = {**registry, **browser_tool_registry()}

    # browser guidance injected as append_system_prompt
    browser_prompt = get_browser_guidance_section(cfg.get("browser_enabled", False))

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
        append_system_prompt=browser_prompt or None,
    )


def run_agent(prompt: str, session_id: str | None, cfg: dict) -> None:
    """Worker function — runs in a background thread."""
    try:
        agent = build_agent(cfg)
        if session_id:
            stored = load_agent_session(
                session_id,
                directory=Path(".port_sessions/agent").resolve(),
            )
            result = agent.resume(prompt, stored)
        else:
            result = agent.run(prompt)
        result_holder["result"] = result
        result_holder["error"] = None
        result_holder["tb"] = None
    except Exception as exc:
        result_holder["result"] = None
        result_holder["error"] = str(exc)
        result_holder["tb"] = traceback.format_exc()


def cfg_from_state(state, input_cost: float = 0.0, output_cost: float = 0.0) -> dict:
    """Snapshot relevant keys from st.session_state (safe for threads)."""
    return {
        **{k: state[k] for k in ("model", "base_url", "api_key", "cwd", "max_turns",
                                  "allow_write", "allow_shell", "unsafe")},
        "input_cost_per_million":  input_cost,
        "output_cost_per_million": output_cost,
        "browser_enabled": state.get("browser_enabled", False),
    }
