from __future__ import annotations

import json
import os
import sys
import time
import threading
import traceback
from pathlib import Path

import streamlit as st

# ── load .env ─────────────────────────────────────────────────────────────────
def _load_env():
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip().replace("\r", "")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

_load_env()

def _save_env(base_url: str, api_key: str, model: str):
    Path(".env").write_text(
        f"OPENAI_BASE_URL={base_url}\n"
        f"OPENAI_API_KEY={api_key}\n"
        f"OPENAI_MODEL={model}\n",
        encoding="utf-8",
    )
    os.environ["OPENAI_BASE_URL"] = base_url
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_MODEL"] = model

# ── src path ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from src.agent_runtime import LocalCodingAgent
from src.agent_types import AgentRuntimeConfig, AgentPermissions, ModelConfig
from src.session_store import load_agent_session

# ── fetch models from provider ────────────────────────────────────────────────
import urllib.request

@st.cache_data(ttl=120, show_spinner=False)
def _fetch_models(base_url: str, api_key: str) -> list[str]:
    """Call GET /v1/models and return sorted model id list."""
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        # already has /v1 or ends with it
        pass
    url = url + "/models"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        models = [m["id"] for m in data.get("data", []) if isinstance(m.get("id"), str)]
        return sorted(models)
    except Exception as exc:
        return [f"__error__:{exc}"]

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Claw Code Agent",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background: #0d1117; color: #e6edf3; }
  .chat-bubble-user {
    background: #1f6feb22;
    border: 1px solid #1f6feb55;
    border-radius: 12px 12px 4px 12px;
    padding: 12px 16px; margin: 8px 0;
    max-width: 80%; margin-left: auto; color: #e6edf3;
  }
  .chat-bubble-assistant {
    background: #161b2233;
    border: 1px solid #30363d;
    border-radius: 12px 12px 12px 4px;
    padding: 12px 16px; margin: 8px 0;
    max-width: 90%; color: #e6edf3;
  }
  .chat-bubble-error {
    background: #ff000015;
    border: 1px solid #f8514955;
    border-radius: 12px 12px 12px 4px;
    padding: 12px 16px; margin: 8px 0;
    max-width: 90%; color: #f85149;
  }
  .token-badge {
    display: inline-block; background: #21262d;
    border: 1px solid #30363d; border-radius: 20px;
    padding: 2px 10px; font-size: 11px; color: #8b949e; margin-top: 6px;
  }
  .status-thinking { color: #f0883e; font-size: 13px; font-style: italic; }
  .status-writing  { color: #3fb950; font-size: 13px; font-style: italic; }
  .status-tool     { color: #a371f7; font-size: 13px; font-style: italic; }
  .log-entry { font-family: monospace; font-size: 12px; padding: 4px 0; border-bottom: 1px solid #21262d; }
  .log-error { color: #f85149; }
  .log-info  { color: #8b949e; }
  .session-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 10px 14px; margin: 6px 0; cursor: pointer;
  }
  .session-active { border-color: #1f6feb !important; }
</style>
""", unsafe_allow_html=True)

# ── state init ────────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "messages": [],
        "agent_session_id": None,
        "status": "idle",
        "status_text": "",
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost": 0.0,
        "allow_write": False,
        "allow_shell": False,
        "unsafe": False,
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "max_turns": 12,
        "cwd": str(Path(".").resolve()),
        "logs": [],   # {level, text, ts}
        "active_tab": "chat",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

def _log(level: str, text: str):
    st.session_state.logs.append({
        "level": level,
        "text": text,
        "ts": time.strftime("%H:%M:%S"),
    })

# ── agent runner ──────────────────────────────────────────────────────────────
_result_holder: dict = {}

def _build_agent(cfg: dict) -> LocalCodingAgent:
    return LocalCodingAgent(
        model_config=ModelConfig(
            model=cfg["model"],
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
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
    )

def _run_agent(prompt: str, session_id: str | None, cfg: dict):
    try:
        agent = _build_agent(cfg)
        if session_id:
            stored = load_agent_session(
                session_id,
                directory=Path(".port_sessions/agent").resolve(),
            )
            result = agent.resume(prompt, stored)
        else:
            result = agent.run(prompt)
        _result_holder["result"] = result
        _result_holder["error"] = None
        _result_holder["tb"] = None
    except Exception as exc:
        _result_holder["result"] = None
        _result_holder["error"] = str(exc)
        _result_holder["tb"] = traceback.format_exc()

# ── list saved sessions ───────────────────────────────────────────────────────
def _list_sessions() -> list[dict]:
    sessions_dir = Path(".port_sessions/agent")
    if not sessions_dir.exists():
        return []
    sessions = []
    for f in sorted(sessions_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": f.stem,
                "turns": data.get("turns", "?"),
                "model": data.get("model_config", {}).get("model", "?"),
                "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)),
                "prompt": (data.get("messages") or [{}])[1].get("content", "")[:60] if len(data.get("messages", [])) > 1 else "",
            })
        except Exception:
            pass
    return sessions

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🐾 Claw Code Agent")
    st.markdown("---")

    # Model config
    with st.expander("⚙️ Model Config", expanded=True):
        base_url_input = st.text_input("Base URL", value=st.session_state.base_url, key="sb_base_url")
        api_key_input  = st.text_input("API Key", value=st.session_state.api_key, type="password", key="sb_api_key")

        # model selector: fetch from provider
        col_m, col_r = st.columns([4, 1])
        with col_r:
            st.markdown("<br>", unsafe_allow_html=True)
            do_fetch = st.button("🔄", key="fetch_models", help="Fetch models from provider")

        fetched = _fetch_models(base_url_input, api_key_input)
        has_error = fetched and fetched[0].startswith("__error__:")

        if has_error:
            st.warning(f"Could not fetch models: {fetched[0].replace('__error__:', '')}")
            model_list = [st.session_state.model]
        else:
            model_list = fetched if fetched else [st.session_state.model]

        if do_fetch:
            _fetch_models.clear()
            st.rerun()

        current = st.session_state.model
        idx = model_list.index(current) if current in model_list else 0
        with col_m:
            model_select = st.selectbox("Model", model_list, index=idx, key="sb_model_select")

        custom_model = st.text_input("Or type custom model", value="", placeholder="leave blank to use above", key="sb_custom_model")
        chosen_model = custom_model.strip() if custom_model.strip() else model_select

        if st.button("💾 Save to .env", use_container_width=True):
            _save_env(base_url_input, api_key_input, chosen_model)
            st.session_state.base_url = base_url_input
            st.session_state.api_key  = api_key_input
            st.session_state.model    = chosen_model
            _log("info", f"Saved config: model={chosen_model}, base_url={base_url_input}")
            st.success("Saved to .env")
        else:
            st.session_state.base_url = base_url_input
            st.session_state.api_key  = api_key_input
            st.session_state.model    = chosen_model

    # Permissions
    with st.expander("🔐 Permissions"):
        st.session_state.allow_write = st.checkbox("Allow Write", value=st.session_state.allow_write)
        st.session_state.allow_shell = st.checkbox("Allow Shell", value=st.session_state.allow_shell)
        st.session_state.unsafe      = st.checkbox("Unsafe (destructive shell)", value=st.session_state.unsafe)

    # Runtime
    with st.expander("🔧 Runtime"):
        st.session_state.max_turns = st.slider("Max Turns", 1, 30, st.session_state.max_turns)
        st.session_state.cwd       = st.text_input("Working Directory", value=st.session_state.cwd)

    st.markdown("---")

    # Token usage
    st.markdown("### 📊 Session Usage")
    c1, c2 = st.columns(2)
    c1.metric("Input", f"{st.session_state.total_input_tokens:,}")
    c2.metric("Output", f"{st.session_state.total_output_tokens:,}")
    st.metric("Cost (USD)", f"${st.session_state.total_cost:.6f}")

    st.markdown("---")

    # Slash commands
    st.markdown("### ⚡ Slash Commands")
    slash_cmds = ["/help", "/context", "/tools", "/memory", "/status",
                  "/permissions", "/model", "/clear", "/tasks", "/plan"]
    cols = st.columns(2)
    for i, cmd in enumerate(slash_cmds):
        if cols[i % 2].button(cmd, key=f"slash_{cmd}", use_container_width=True):
            st.session_state["_inject_prompt"] = cmd

    st.markdown("---")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent_session_id = None
        st.session_state.total_input_tokens = 0
        st.session_state.total_output_tokens = 0
        st.session_state.total_cost = 0.0
        st.rerun()

# ── tabs ──────────────────────────────────────────────────────────────────────
tab_chat, tab_sessions, tab_logs = st.tabs(["💬 Chat", "🗂️ Sessions", "🪵 Logs"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: CHAT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    status = st.session_state.status
    if status == "thinking":
        st.markdown('<div class="status-thinking">🤔 Thinking...</div>', unsafe_allow_html=True)
    elif status == "writing":
        st.markdown('<div class="status-writing">✍️ Writing response...</div>', unsafe_allow_html=True)
    elif status == "tool":
        st.markdown(f'<div class="status-tool">🔧 {st.session_state.status_text}</div>', unsafe_allow_html=True)

    if st.session_state.agent_session_id:
        st.caption(f"Session: `{st.session_state.agent_session_id}`")

    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-bubble-user">👤 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            is_error = msg["content"].startswith("❌")
            bubble_class = "chat-bubble-error" if is_error else "chat-bubble-assistant"
            icon = "⚠️" if is_error else "🐾"
            content_html = msg["content"].replace("\n", "<br>")
            tokens_html = ""
            if not is_error and msg.get("input_tokens") is not None:
                stop = msg.get("stop_reason", "")
                stop_badge = f" · {stop}" if stop and stop not in ("stop", "") else ""
                tokens_html = (
                    f'<div class="token-badge">'
                    f'↑ {msg["input_tokens"]:,} in · ↓ {msg["output_tokens"]:,} out'
                    f' · ${msg.get("cost", 0):.6f}{stop_badge}'
                    f'</div>'
                )
            st.markdown(
                f'<div class="{bubble_class}">{icon} {content_html}{tokens_html}</div>',
                unsafe_allow_html=True,
            )

    injected = st.session_state.pop("_inject_prompt", None)
    prompt = st.chat_input("Type a message or /command...", key="chat_input")
    if injected:
        prompt = injected

    if prompt:
        _log("info", f"User: {prompt[:80]}")
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.status = "thinking"
        st.rerun()

    if st.session_state.status == "thinking":
        last_user = next(
            (m["content"] for m in reversed(st.session_state.messages) if m["role"] == "user"),
            None,
        )
        if last_user:
            cfg = {k: st.session_state[k] for k in
                   ("model", "base_url", "api_key", "cwd", "max_turns",
                    "allow_write", "allow_shell", "unsafe")}
            _result_holder.clear()
            t = threading.Thread(target=_run_agent,
                                 args=(last_user, st.session_state.agent_session_id, cfg),
                                 daemon=True)
            t.start()

            dots = 0
            ph = st.empty()
            while t.is_alive():
                dots = (dots + 1) % 4
                ph.markdown(
                    f'<div class="status-thinking">🤔 Thinking{"." * (dots + 1)}</div>',
                    unsafe_allow_html=True,
                )
                time.sleep(0.4)
            ph.empty()
            t.join()

            if _result_holder.get("error"):
                err = _result_holder["error"]
                tb  = _result_holder.get("tb", "")
                _log("error", f"Agent error: {err}")
                if tb:
                    _log("error", tb)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ Error: {err}",
                    "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
                })
            else:
                result = _result_holder["result"]
                st.session_state.agent_session_id = result.session_id
                st.session_state.total_input_tokens += result.usage.input_tokens
                st.session_state.total_output_tokens += result.usage.output_tokens
                st.session_state.total_cost += result.total_cost_usd
                _log("info", f"Response: {result.usage.input_tokens} in / {result.usage.output_tokens} out | stop={result.stop_reason}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result.final_output or "(no output)",
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "cost": result.total_cost_usd,
                    "stop_reason": result.stop_reason or "",
                })

            st.session_state.status = "idle"
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: SESSIONS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sessions:
    st.markdown("### 🗂️ Saved Sessions")
    if st.button("🔄 Refresh", key="refresh_sessions"):
        st.rerun()

    sessions = _list_sessions()
    if not sessions:
        st.info("No saved sessions found in `.port_sessions/agent/`")
    else:
        for s in sessions:
            is_active = s["id"] == st.session_state.agent_session_id
            border = "session-active" if is_active else ""
            active_badge = " 🟢 active" if is_active else ""
            st.markdown(
                f'<div class="session-card {border}">'
                f'<b style="color:#79c0ff">{s["id"][:16]}…</b>{active_badge}<br>'
                f'<span style="color:#8b949e;font-size:12px">'
                f'model: {s["model"]} · turns: {s["turns"]} · {s["mtime"]}</span><br>'
                f'<span style="font-size:12px;color:#e6edf3">{s["prompt"]}…</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            col1, col2 = st.columns([1, 1])
            if col1.button("▶️ Resume this session", key=f"resume_{s['id']}"):
                st.session_state.agent_session_id = s["id"]
                st.session_state.messages = []
                st.session_state.total_input_tokens = 0
                st.session_state.total_output_tokens = 0
                st.session_state.total_cost = 0.0
                _log("info", f"Switched to session {s['id']}")
                st.success(f"Now using session `{s['id'][:16]}…` — type your next message in Chat.")
            if col2.button("🆕 New session from here", key=f"new_{s['id']}"):
                st.session_state.agent_session_id = None
                st.session_state.messages = []
                st.session_state.total_input_tokens = 0
                st.session_state.total_output_tokens = 0
                st.session_state.total_cost = 0.0
                _log("info", "Started new session")
                st.success("New session started — type your first message in Chat.")

    st.markdown("---")
    if st.button("🆕 Start fresh session", key="new_session_btn", use_container_width=True):
        st.session_state.agent_session_id = None
        st.session_state.messages = []
        st.session_state.total_input_tokens = 0
        st.session_state.total_output_tokens = 0
        st.session_state.total_cost = 0.0
        st.success("New session ready.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: LOGS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_logs:
    st.markdown("### 🪵 Logs")
    col1, col2 = st.columns([1, 1])
    if col1.button("🔄 Refresh", key="refresh_logs"):
        st.rerun()
    if col2.button("🗑️ Clear logs", key="clear_logs"):
        st.session_state.logs = []
        st.rerun()

    filter_level = st.radio("Filter", ["all", "error", "info"], horizontal=True, key="log_filter")

    logs = st.session_state.logs[::-1]  # newest first
    if filter_level != "all":
        logs = [l for l in logs if l["level"] == filter_level]

    if not logs:
        st.info("No logs yet.")
    else:
        for entry in logs:
            css = "log-error" if entry["level"] == "error" else "log-info"
            icon = "🔴" if entry["level"] == "error" else "⚪"
            text = entry["text"].replace("\n", "<br>").replace("<", "&lt;")
            st.markdown(
                f'<div class="log-entry {css}">{icon} <b>{entry["ts"]}</b> {text}</div>',
                unsafe_allow_html=True,
            )
