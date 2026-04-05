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
  /* fixed input at bottom — left set by JS */
  [data-testid="stChatInput"] {
    position: fixed !important;
    bottom: 0 !important;
    right: 0 !important;
    z-index: 999 !important;
    background: #0d1117 !important;
    padding: 12px 24px 16px 24px !important;
    border-top: 1px solid #30363d !important;
  }
  /* space for fixed input at bottom */
  [data-testid="stMainBlockContainer"] {
    padding-bottom: 90px !important;
  }
  .log-entry { font-family: monospace; font-size: 12px; padding: 4px 0; border-bottom: 1px solid #21262d; }
  .log-error { color: #f85149; }
  .log-info  { color: #8b949e; }
  .session-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 10px 14px; margin: 6px 0; cursor: pointer;
  }
  .session-active { border-color: #1f6feb !important; }
  /* file tree */
  .tree-file {
    font-family: monospace; font-size: 12px; color: #e6edf3;
    padding: 2px 0 2px 4px; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  .tree-file:hover { color: #79c0ff; }
  .tree-dir  { font-family: monospace; font-size: 12px; color: #79c0ff; font-weight: 600; }
  .tree-cwd  {
    background: #1f6feb22; border: 1px solid #1f6feb55;
    border-radius: 6px; padding: 6px 10px; margin-bottom: 8px;
    font-family: monospace; font-size: 12px; color: #79c0ff;
    word-break: break-all;
  }
  .tree-nav-btn { font-size: 11px; }
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
        "tree_open": False,
        "tree_browse_path": str(Path(".").resolve()),
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

# ── JS: keep chat input aligned with sidebar ──────────────────────────────────
st.components.v1.html("""
<script>
(function() {
  function getSidebarWidth() {
    const sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
    if (!sidebar) return 0;
    const w = sidebar.getBoundingClientRect().width;
    return w > 50 ? w : 0;
  }

  function syncAll() {
    const w = getSidebarWidth();

    // fix chat input left edge
    const input = window.parent.document.querySelector('[data-testid="stChatInput"]');
    if (input) input.style.left = w + 'px';

    // fix tab bar below streamlit header (60px)
    const tabs = window.parent.document.querySelector('[data-testid="stTabs"]');
    const tabBar = tabs ? tabs.firstElementChild : null;
    if (tabBar) {
      tabBar.style.position   = 'fixed';
      tabBar.style.top        = '60px';
      tabBar.style.left       = w + 'px';
      tabBar.style.right      = '0';
      tabBar.style.zIndex     = '997';
      tabBar.style.background = '#0d1117';
      tabBar.style.borderBottom = '1px solid #30363d';
      tabBar.style.padding    = '0 24px';
    }

    // push block container below header(60) + tabbar(~42)
    const block = window.parent.document.querySelector('[data-testid="stMainBlockContainer"]');
    if (block) {
      block.style.paddingTop = '110px';
      block.style.overflow = 'visible';
    }

    // ensure the main section doesn't clip scroll
    const main = window.parent.document.querySelector('[data-testid="stMain"]');
    if (main) main.style.overflow = 'visible';
  }

  setInterval(syncAll, 100);
})();
</script>
""", height=0)

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
def _load_session_messages(session_id: str) -> list[dict]:
    """Load messages from a saved session and convert to chat format."""
    try:
        f = Path(".port_sessions/agent") / f"{session_id}.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        chat_msgs = []
        for m in data.get("messages", []):
            role = m.get("role", "")
            content = m.get("content", "")
            if not content or role == "system":
                continue
            # content can be a list of blocks (tool calls etc)
            if isinstance(content, list):
                text = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            else:
                text = str(content)
            if not text.strip():
                continue
            if role == "user":
                # skip system-reminder injections
                if text.strip().startswith("<system-reminder>"):
                    continue
                chat_msgs.append({"role": "user", "content": text})
            elif role == "assistant":
                chat_msgs.append({
                    "role": "assistant",
                    "content": text,
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost": 0.0,
                    "stop_reason": "",
                })
        return chat_msgs
    except Exception:
        return []

def _relative_time(mtime: float) -> str:
    diff = time.time() - mtime
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff/60)}m ago"
    if diff < 86400:
        return f"{int(diff/3600)}h ago"
    if diff < 86400 * 7:
        return f"{int(diff/86400)}d ago"
    return time.strftime("%b %d, %Y", time.localtime(mtime))

def _list_sessions() -> list[dict]:
    sessions_dir = Path(".port_sessions/agent")
    if not sessions_dir.exists():
        return []
    sessions = []
    for f in sorted(sessions_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            msgs = data.get("messages", [])
            # count only user/assistant messages (not system)
            user_msgs = sum(1 for m in msgs if m.get("role") == "user"
                           and not str(m.get("content","")).strip().startswith("<system-reminder>"))
            asst_msgs = sum(1 for m in msgs if m.get("role") == "assistant")
            # first user message as preview
            first_user = next(
                (str(m.get("content",""))[:80] for m in msgs
                 if m.get("role") == "user"
                 and not str(m.get("content","")).strip().startswith("<system-reminder>")),
                ""
            )
            mtime = f.stat().st_mtime
            sessions.append({
                "id": f.stem,
                "turns": data.get("turns", "?"),
                "model": data.get("model_config", {}).get("model", "?"),
                "mtime": mtime,
                "mtime_rel": _relative_time(mtime),
                "mtime_abs": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
                "user_msgs": user_msgs,
                "asst_msgs": asst_msgs,
                "total_msgs": user_msgs + asst_msgs,
                "prompt": first_user,
                "cost": data.get("total_cost_usd", 0.0),
            })
        except Exception:
            pass
    return sessions
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

# ── file tree helpers ─────────────────────────────────────────────────────────
IGNORE_DIRS = {".git", "__pycache__", ".port_sessions", "venv", ".venv", "node_modules", ".mypy_cache"}
FILE_ICONS = {
    ".py": "🐍", ".md": "📝", ".json": "📋", ".txt": "📄",
    ".sh": "⚙️", ".env": "🔑", ".toml": "⚙️", ".yaml": "⚙️", ".yml": "⚙️",
    ".js": "🟨", ".ts": "🔷", ".html": "🌐", ".css": "🎨",
    ".png": "🖼️", ".jpg": "🖼️", ".gif": "🖼️",
}

def _file_icon(name: str) -> str:
    ext = Path(name).suffix.lower()
    return FILE_ICONS.get(ext, "📄")

def _safe_is_dir(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False

def _safe_is_file(p: Path) -> bool:
    try:
        return p.is_file()
    except OSError:
        return False

def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return sorted(path.iterdir(), key=lambda p: (not _safe_is_dir(p), p.name.lower()))
    except OSError:
        return []

def _render_tree(path: Path, depth: int = 0, max_depth: int = 6):
    """Render directory tree recursively using st.expander for folders."""
    if depth > max_depth:
        return

    entries = _safe_iterdir(path)
    dirs  = [e for e in entries if _safe_is_dir(e)  and e.name not in IGNORE_DIRS]
    files = [e for e in entries if _safe_is_file(e)]

    for d in dirs:
        with st.expander(f"📁 {d.name}", expanded=False):
            # "Set as CWD" button inside each folder
            c1, c2 = st.columns([3, 1])
            c1.markdown(f'<span style="font-size:11px;color:#8b949e">{str(d)}</span>', unsafe_allow_html=True)
            if c2.button("📌 Use", key=f"cwd_{d}", help="Set as working directory"):
                st.session_state.cwd = str(d)
                st.session_state.tree_browse_path = str(d)
                _log("info", f"CWD changed to {d}")
                st.rerun()
            _render_tree(d, depth + 1, max_depth)

    for f in files:
        icon = _file_icon(f.name)
        st.markdown(f'<div class="tree-file">{icon} {f.name}</div>', unsafe_allow_html=True)

# ── tabs ──────────────────────────────────────────────────────────────────────
tab_chat, tab_tree, tab_sessions, tab_logs = st.tabs(["💬 Chat", "📁 Explorer", "🗂️ Sessions", "🪵 Logs"])

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

    msgs_container = st.container(height=600, border=False)
    with msgs_container:
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                is_error = msg["content"].startswith("❌")
                with st.chat_message("assistant"):
                    if is_error:
                        st.error(msg["content"])
                    else:
                        st.markdown(msg["content"])
                        if msg.get("input_tokens") is not None:
                            stop = msg.get("stop_reason", "")
                            stop_badge = f" · {stop}" if stop and stop not in ("stop", "") else ""
                            st.markdown(
                                f'<div class="token-badge">'
                                f'↑ {msg["input_tokens"]:,} in · ↓ {msg["output_tokens"]:,} out'
                                f' · ${msg.get("cost", 0):.6f}{stop_badge}'
                                f'</div>',
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
# TAB: EXPLORER
# ═══════════════════════════════════════════════════════════════════════════════
with tab_tree:
    st.markdown("### 📁 Explorer")

    browse = Path(st.session_state.tree_browse_path)

    # breadcrumb + navigation bar
    parts = browse.parts
    st.markdown(
        f'<div class="tree-cwd">📍 {browse}</div>',
        unsafe_allow_html=True,
    )

    nav_cols = st.columns([1, 1, 1, 3])
    if nav_cols[0].button("⬆️ Up", key="tree_up", use_container_width=True):
        parent = browse.parent
        if parent != browse:
            st.session_state.tree_browse_path = str(parent)
            st.rerun()

    if nav_cols[1].button("🏠 Home", key="tree_home", use_container_width=True):
        st.session_state.tree_browse_path = str(Path.home())
        st.rerun()

    if nav_cols[2].button("📌 Set CWD", key="tree_set_cwd", use_container_width=True,
                          help="Use current browse path as agent working directory"):
        st.session_state.cwd = str(browse)
        _log("info", f"CWD set to {browse}")
        st.success(f"Working directory set to `{browse}`")

    custom_path = nav_cols[3].text_input(
        "Go to path", value="", placeholder="Paste any path…",
        key="tree_custom_path", label_visibility="collapsed",
    )
    if custom_path.strip() and Path(custom_path.strip()).exists():
        st.session_state.tree_browse_path = str(Path(custom_path.strip()).resolve())
        st.rerun()

    st.caption(f"Agent CWD: `{st.session_state.cwd}`")
    st.markdown("---")

    # render tree from browse path
    browse_path = Path(st.session_state.tree_browse_path)
    if not browse_path.exists():
        st.error(f"Path does not exist: {browse_path}")
    else:
        # top-level dirs as expanders, files listed below
        try:
            entries = sorted(browse_path.iterdir(), key=lambda p: (not _safe_is_dir(p), p.name.lower()))
        except OSError:
            entries = []
            st.error("Permission denied.")

        dirs  = [e for e in entries if _safe_is_dir(e)  and e.name not in IGNORE_DIRS]
        files = [e for e in entries if _safe_is_file(e)]

        for d in dirs:
            with st.expander(f"📁 {d.name}"):
                hc1, hc2, hc3 = st.columns([3, 1, 1])
                hc1.markdown(f'<span style="font-size:11px;color:#8b949e">{d}</span>', unsafe_allow_html=True)
                if hc2.button("📌 CWD", key=f"cwd_top_{d.name}", help="Set as agent working directory"):
                    st.session_state.cwd = str(d)
                    _log("info", f"CWD changed to {d}")
                    st.rerun()
                if hc3.button("🔍 Open", key=f"open_top_{d.name}", help="Browse into this folder"):
                    st.session_state.tree_browse_path = str(d)
                    st.rerun()
                _render_tree(d, depth=1)

        if files:
            st.markdown("**Files**")
            for f in files:
                icon = _file_icon(f.name)
                try:
                    size = f.stat().st_size
                    size_str = f"{size/1024:.1f} KB" if size >= 1024 else f"{size} B"
                except OSError:
                    size_str = "?"
                st.markdown(
                    f'<div class="tree-file">{icon} {f.name} '
                    f'<span style="color:#8b949e;font-size:10px">{size_str}</span></div>',
                    unsafe_allow_html=True,
                )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB: SESSIONS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sessions:
    hc1, hc2, hc3 = st.columns([3, 1, 1])
    hc1.markdown("### 🗂️ Sessions")
    if hc2.button("🔄 Refresh", key="refresh_sessions", use_container_width=True):
        st.rerun()
    if hc3.button("🆕 New", key="new_session_btn", use_container_width=True):
        st.session_state.agent_session_id = None
        st.session_state.messages = []
        st.session_state.total_input_tokens = 0
        st.session_state.total_output_tokens = 0
        st.session_state.total_cost = 0.0
        st.success("New session ready.")

    sessions = _list_sessions()
    if not sessions:
        st.info("No saved sessions found in `.port_sessions/agent/`")
    else:
        st.caption(f"{len(sessions)} session(s) found")
        scroll = st.container(height=600, border=False)
        with scroll:
            for s in sessions:
                is_active = s["id"] == st.session_state.agent_session_id
                border_color = "#1f6feb" if is_active else "#30363d"
                active_badge = "🟢 active · " if is_active else ""

                st.markdown(
                    f"""<div style="background:#161b22;border:1px solid {border_color};
                    border-radius:8px;padding:10px 14px;margin:6px 0">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                      <span style="color:#79c0ff;font-family:monospace;font-size:12px">
                        {s['id'][:20]}…
                      </span>
                      <span style="color:#8b949e;font-size:11px" title="{s['mtime_abs']}">
                        🕐 {s['mtime_rel']}
                      </span>
                    </div>
                    <div style="margin:4px 0;font-size:12px;color:#8b949e">
                      {active_badge}🤖 {s['model']} &nbsp;·&nbsp;
                      💬 {s['total_msgs']} msgs ({s['user_msgs']}↑ {s['asst_msgs']}↓) &nbsp;·&nbsp;
                      🔄 {s['turns']} turns &nbsp;·&nbsp;
                      💰 ${s['cost']:.4f}
                    </div>
                    <div style="font-size:12px;color:#e6edf3;margin-top:4px;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                      💬 {s['prompt']}
                    </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2)
                if c1.button("▶️ Resume", key=f"resume_{s['id']}", use_container_width=True):
                    st.session_state.agent_session_id = s["id"]
                    st.session_state.messages = _load_session_messages(s["id"])
                    st.session_state.total_input_tokens = 0
                    st.session_state.total_output_tokens = 0
                    st.session_state.total_cost = 0.0
                    _log("info", f"Resumed session {s['id']}")
                    st.success(f"Session loaded — continue in Chat.")
                if c2.button("🆕 Fork", key=f"fork_{s['id']}", use_container_width=True,
                             help="Start a new session (discard this one)"):
                    st.session_state.agent_session_id = None
                    st.session_state.messages = []
                    st.session_state.total_input_tokens = 0
                    st.session_state.total_output_tokens = 0
                    st.session_state.total_cost = 0.0
                    _log("info", "Started new session")
                    st.success("New session started.")

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
