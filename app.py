from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path
import streamlit as st

# ── load .env (strip quotes and \r) ──────────────────────────────────────────
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

# ── add src to path ───────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from src.agent_runtime import LocalCodingAgent
from src.agent_types import AgentRuntimeConfig, AgentPermissions, BudgetConfig, ModelConfig
from src.session_store import load_agent_session

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Claw Code Agent",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background: #0d1117; color: #e6edf3; }
  .chat-bubble-user {
    background: #1f6feb22;
    border: 1px solid #1f6feb55;
    border-radius: 12px 12px 4px 12px;
    padding: 12px 16px;
    margin: 8px 0;
    max-width: 80%;
    margin-left: auto;
    color: #e6edf3;
  }
  .chat-bubble-assistant {
    background: #161b2222;
    border: 1px solid #30363d;
    border-radius: 12px 12px 12px 4px;
    padding: 12px 16px;
    margin: 8px 0;
    max-width: 90%;
    color: #e6edf3;
  }
  .token-badge {
    display: inline-block;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 11px;
    color: #8b949e;
    margin-top: 6px;
  }
  .status-thinking {
    color: #f0883e;
    font-size: 13px;
    font-style: italic;
    animation: pulse 1.2s infinite;
  }
  .status-writing {
    color: #3fb950;
    font-size: 13px;
    font-style: italic;
  }
  .status-tool {
    color: #a371f7;
    font-size: 13px;
    font-style: italic;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .sidebar-section { margin-bottom: 16px; }
  .metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 4px 0;
  }
  .slash-cmd {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
    font-family: monospace;
    font-size: 12px;
    color: #79c0ff;
    cursor: pointer;
    display: inline-block;
    margin: 2px;
  }
</style>
""", unsafe_allow_html=True)

# ── session state init ────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "messages": [],           # {role, content, tokens, cost, stop_reason, session_id}
        "agent_session_id": None,
        "status": "idle",          # idle | thinking | writing | tool
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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── build agent ───────────────────────────────────────────────────────────────
def _build_agent() -> LocalCodingAgent:
    return LocalCodingAgent(
        model_config=ModelConfig(
            model=st.session_state.model,
            base_url=st.session_state.base_url,
            api_key=st.session_state.api_key,
        ),
        runtime_config=AgentRuntimeConfig(
            cwd=Path(st.session_state.cwd).resolve(),
            max_turns=st.session_state.max_turns,
            permissions=AgentPermissions(
                allow_file_write=st.session_state.allow_write,
                allow_shell_commands=st.session_state.allow_shell,
                allow_destructive_shell_commands=st.session_state.unsafe,
            ),
        ),
    )

# ── run agent in thread ───────────────────────────────────────────────────────
_result_holder: dict = {}

def _run_agent(prompt: str, session_id: str | None):
    try:
        agent = _build_agent()
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
    except Exception as exc:
        _result_holder["result"] = None
        _result_holder["error"] = str(exc)

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🐾 Claw Code Agent")
    st.markdown("---")

    # Model config
    with st.expander("⚙️ Model Config", expanded=True):
        st.session_state.model = st.text_input("Model", value=st.session_state.model)
        st.session_state.base_url = st.text_input("Base URL", value=st.session_state.base_url)
        st.session_state.api_key = st.text_input("API Key", value=st.session_state.api_key, type="password")

    # Permissions
    with st.expander("🔐 Permissions"):
        st.session_state.allow_write = st.checkbox("Allow Write", value=st.session_state.allow_write)
        st.session_state.allow_shell = st.checkbox("Allow Shell", value=st.session_state.allow_shell)
        st.session_state.unsafe = st.checkbox("Unsafe (destructive shell)", value=st.session_state.unsafe)

    # Runtime
    with st.expander("🔧 Runtime"):
        st.session_state.max_turns = st.slider("Max Turns", 1, 30, st.session_state.max_turns)
        st.session_state.cwd = st.text_input("Working Directory", value=st.session_state.cwd)

    st.markdown("---")

    # Token usage
    st.markdown("### 📊 Session Usage")
    col1, col2 = st.columns(2)
    col1.metric("Input tokens", f"{st.session_state.total_input_tokens:,}")
    col2.metric("Output tokens", f"{st.session_state.total_output_tokens:,}")
    st.metric("Total cost (USD)", f"${st.session_state.total_cost:.6f}")

    st.markdown("---")

    # Slash commands
    st.markdown("### ⚡ Slash Commands")
    slash_cmds = ["/help", "/context", "/tools", "/memory", "/status", "/permissions", "/model", "/clear", "/tasks", "/plan"]
    cols = st.columns(2)
    for i, cmd in enumerate(slash_cmds):
        if cols[i % 2].button(cmd, key=f"slash_{cmd}", use_container_width=True):
            st.session_state["_inject_prompt"] = cmd

    st.markdown("---")

    # Clear chat
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent_session_id = None
        st.session_state.total_input_tokens = 0
        st.session_state.total_output_tokens = 0
        st.session_state.total_cost = 0.0
        st.rerun()

# ── main chat area ────────────────────────────────────────────────────────────
st.markdown("### 💬 Chat")

# Status indicator
status = st.session_state.status
if status == "thinking":
    st.markdown('<div class="status-thinking">🤔 Thinking...</div>', unsafe_allow_html=True)
elif status == "writing":
    st.markdown('<div class="status-writing">✍️ Writing response...</div>', unsafe_allow_html=True)
elif status == "tool":
    st.markdown(f'<div class="status-tool">🔧 {st.session_state.status_text}</div>', unsafe_allow_html=True)

# Render messages
chat_container = st.container()
with chat_container:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-bubble-user">👤 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            content_html = msg["content"].replace("\n", "<br>")
            tokens_html = ""
            if msg.get("input_tokens") is not None:
                stop = msg.get("stop_reason", "")
                stop_badge = f" · {stop}" if stop and stop != "stop" else ""
                tokens_html = (
                    f'<div class="token-badge">'
                    f'↑ {msg["input_tokens"]:,} in · ↓ {msg["output_tokens"]:,} out'
                    f' · ${msg.get("cost", 0):.6f}{stop_badge}'
                    f'</div>'
                )
            st.markdown(
                f'<div class="chat-bubble-assistant">🐾 {content_html}{tokens_html}</div>',
                unsafe_allow_html=True,
            )

# ── input ─────────────────────────────────────────────────────────────────────
injected = st.session_state.pop("_inject_prompt", None)
prompt = st.chat_input("Type a message or /command...", key="chat_input")
if injected:
    prompt = injected

if prompt:
    # append user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.status = "thinking"
    st.rerun()

# ── process pending (status != idle) ─────────────────────────────────────────
if st.session_state.status == "thinking":
    last_user = next(
        (m["content"] for m in reversed(st.session_state.messages) if m["role"] == "user"),
        None,
    )
    if last_user:
        _result_holder.clear()
        t = threading.Thread(
            target=_run_agent,
            args=(last_user, st.session_state.agent_session_id),
            daemon=True,
        )
        t.start()

        # poll with status updates
        dots = 0
        placeholder = st.empty()
        while t.is_alive():
            dots = (dots + 1) % 4
            placeholder.markdown(
                f'<div class="status-thinking">🤔 Thinking{"." * (dots + 1)}</div>',
                unsafe_allow_html=True,
            )
            time.sleep(0.4)
        placeholder.empty()
        t.join()

        if _result_holder.get("error"):
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"❌ Error: {_result_holder['error']}",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
            })
        else:
            result = _result_holder["result"]
            st.session_state.agent_session_id = result.session_id
            st.session_state.total_input_tokens += result.usage.input_tokens
            st.session_state.total_output_tokens += result.usage.output_tokens
            st.session_state.total_cost += result.total_cost_usd
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
