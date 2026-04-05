from __future__ import annotations

import sys
import time
import threading
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ── bootstrap ─────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from ui.env_config import load_env, save_env, fetch_models
from ui.state     import init_state, log, reset_session
from ui.agent     import run_agent, result_holder, cfg_from_state
from ui.sessions  import list_sessions, load_messages, load_usage
from ui.icons     import file_icon, IGNORE_DIRS, SLASH_COMMANDS, ROLE_ICONS

load_env()

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Claw Code Agent",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── inject CSS ────────────────────────────────────────────────────────────────
_css = (Path(__file__).parent / "ui" / "styles.css").read_text(encoding="utf-8")
st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)

# ── state ─────────────────────────────────────────────────────────────────────
init_state()

# ── JS: sync input + tabbar with sidebar width ────────────────────────────────
components.html("""
<script>
(function() {
  function getSidebarWidth() {
    const sb = window.parent.document.querySelector('[data-testid="stSidebar"]');
    if (!sb) return 0;
    const w = sb.getBoundingClientRect().width;
    return w > 50 ? w : 0;
  }
  function sync() {
    const w     = getSidebarWidth();
    const input = window.parent.document.querySelector('[data-testid="stChatInput"]');
    const tabs  = window.parent.document.querySelector('[data-testid="stTabs"]');
    const bar   = tabs ? tabs.firstElementChild : null;
    const block = window.parent.document.querySelector('[data-testid="stMainBlockContainer"]');
    const main  = window.parent.document.querySelector('[data-testid="stMain"]');

    if (input) input.style.left = w + 'px';

    if (bar) {
      bar.style.position    = 'fixed';
      bar.style.top         = '60px';
      bar.style.left        = w + 'px';
      bar.style.right       = '0';
      bar.style.zIndex      = '997';
      bar.style.background  = '#0d1117';
      bar.style.borderBottom = '1px solid #30363d';
      bar.style.padding     = '0 24px';
    }
    if (block) { block.style.paddingTop = '110px'; block.style.overflow = 'visible'; }
    if (main)  { main.style.overflow = 'visible'; }
  }
  setInterval(sync, 100);
})();
</script>
""", height=0)

# ── helpers ───────────────────────────────────────────────────────────────────
def _safe_is_dir(p: Path) -> bool:
    try: return p.is_dir()
    except OSError: return False

def _safe_is_file(p: Path) -> bool:
    try: return p.is_file()
    except OSError: return False

def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return sorted(path.iterdir(), key=lambda p: (not _safe_is_dir(p), p.name.lower()))
    except OSError:
        return []

def _render_tree(path: Path, depth: int = 0, max_depth: int = 6) -> None:
    if depth > max_depth:
        return
    entries = _safe_iterdir(path)
    dirs  = [e for e in entries if _safe_is_dir(e)  and e.name not in IGNORE_DIRS]
    files = [e for e in entries if _safe_is_file(e)]
    for d in dirs:
        with st.expander(f"📁 {d.name}", expanded=False):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f'<span style="font-size:11px;color:#8b949e">{d}</span>', unsafe_allow_html=True)
            if c2.button("📌", key=f"cwd_{d}", help="Set as CWD"):
                st.session_state.cwd = str(d)
                st.session_state.tree_browse_path = str(d)
                log("info", f"CWD → {d}")
                st.rerun()
            _render_tree(d, depth + 1, max_depth)
    for f in files:
        try:
            sz = f.stat().st_size
            sz_str = f"{sz/1024:.1f} KB" if sz >= 1024 else f"{sz} B"
        except OSError:
            sz_str = "?"
        st.markdown(
            f'<div class="tree-file">{file_icon(f.name)} {f.name} '
            f'<span style="color:#8b949e;font-size:10px">{sz_str}</span></div>',
            unsafe_allow_html=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🐾 Claw Code Agent")
    st.markdown("---")

    with st.expander("⚙️ Model Config", expanded=True):
        base_url_input = st.text_input("Base URL", value=st.session_state.base_url, key="sb_base_url")
        api_key_input  = st.text_input("API Key",  value=st.session_state.api_key,  type="password", key="sb_api_key")

        col_m, col_r = st.columns([4, 1])
        with col_r:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄", key="fetch_models", help="Refresh model list"):
                fetch_models.clear()
                st.rerun()

        fetched   = fetch_models(base_url_input, api_key_input)
        has_error = fetched and fetched[0].startswith("__error__:")
        if has_error:
            st.warning(f"Could not fetch models: {fetched[0].replace('__error__:', '')}")
            model_list = [st.session_state.model]
        else:
            model_list = fetched or [st.session_state.model]

        current = st.session_state.model
        idx = model_list.index(current) if current in model_list else 0
        with col_m:
            model_select = st.selectbox("Model", model_list, index=idx, key="sb_model_select")

        custom_model = st.text_input("Custom model", value="", placeholder="leave blank to use above", key="sb_custom_model")
        chosen_model = custom_model.strip() if custom_model.strip() else model_select

        if st.button("💾 Save to .env", use_container_width=True):
            save_env(base_url_input, api_key_input, chosen_model)
            st.session_state.base_url = base_url_input
            st.session_state.api_key  = api_key_input
            st.session_state.model    = chosen_model
            log("info", f"Saved: model={chosen_model}")
            st.success("Saved to .env")
        else:
            st.session_state.base_url = base_url_input
            st.session_state.api_key  = api_key_input
            st.session_state.model    = chosen_model

    with st.expander("🔐 Permissions"):
        st.session_state.allow_write = st.checkbox("Allow Write", value=st.session_state.allow_write)
        st.session_state.allow_shell = st.checkbox("Allow Shell", value=st.session_state.allow_shell)
        st.session_state.unsafe      = st.checkbox("Unsafe (destructive shell)", value=st.session_state.unsafe)

    with st.expander("🔧 Runtime"):
        st.session_state.max_turns = st.slider("Max Turns", 1, 30, st.session_state.max_turns)
        st.session_state.cwd       = st.text_input("Working Directory", value=st.session_state.cwd)

    st.markdown("---")
    st.markdown("### 📊 Session Usage")
    c1, c2 = st.columns(2)
    c1.metric("Input",  f"{st.session_state.total_input_tokens:,}")
    c2.metric("Output", f"{st.session_state.total_output_tokens:,}")
    st.metric("Cost (USD)", f"${st.session_state.total_cost:.6f}")

    st.markdown("---")
    st.markdown("### ⚡ Slash Commands")
    cols = st.columns(2)
    for i, cmd in enumerate(SLASH_COMMANDS):
        if cols[i % 2].button(cmd, key=f"slash_{cmd}", use_container_width=True):
            st.session_state["_inject_prompt"] = cmd

    st.markdown("---")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        reset_session()
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_chat, tab_tree, tab_sessions, tab_logs = st.tabs(["💬 Chat", "📁 Explorer", "🗂️ Sessions", "🪵 Logs"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB: CHAT
# ─────────────────────────────────────────────────────────────────────────────
with tab_chat:
    status = st.session_state.status
    if status == "thinking":
        st.markdown('<div class="status-thinking">🤔 Thinking...</div>', unsafe_allow_html=True)

    if st.session_state.agent_session_id:
        st.caption(f"Session: `{st.session_state.agent_session_id}`")

    msgs_box = st.container(height=600, border=False)
    with msgs_box:
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                with st.chat_message("assistant"):
                    if msg["content"].startswith("❌"):
                        st.error(msg["content"])
                    else:
                        st.markdown(msg["content"])
                        if msg.get("input_tokens") is not None:
                            stop = msg.get("stop_reason", "")
                            badge = f" · {stop}" if stop and stop not in ("stop", "") else ""
                            st.markdown(
                                f'<div class="token-badge">'
                                f'↑ {msg["input_tokens"]:,} in · ↓ {msg["output_tokens"]:,} out'
                                f' · ${msg.get("cost", 0):.6f}{badge}</div>',
                                unsafe_allow_html=True,
                            )

    injected = st.session_state.pop("_inject_prompt", None)
    prompt   = st.chat_input("Type a message or /command…", key="chat_input")
    if injected:
        prompt = injected

    if prompt:
        log("info", f"User: {prompt[:80]}")
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.status = "thinking"
        st.rerun()

    if st.session_state.status == "thinking":
        last_user = next(
            (m["content"] for m in reversed(st.session_state.messages) if m["role"] == "user"),
            None,
        )
        if last_user:
            cfg = cfg_from_state(st.session_state)
            result_holder.clear()
            t = threading.Thread(
                target=run_agent,
                args=(last_user, st.session_state.agent_session_id, cfg),
                daemon=True,
            )
            t.start()

            dots, ph = 0, st.empty()
            while t.is_alive():
                dots = (dots + 1) % 4
                ph.markdown(
                    f'<div class="status-thinking">🤔 Thinking{"." * (dots + 1)}</div>',
                    unsafe_allow_html=True,
                )
                time.sleep(0.4)
            ph.empty()
            t.join()

            if result_holder.get("error"):
                err = result_holder["error"]
                log("error", f"Agent error: {err}")
                if result_holder.get("tb"):
                    log("error", result_holder["tb"])
                st.session_state.messages.append({
                    "role": "assistant", "content": f"❌ Error: {err}",
                    "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
                })
            else:
                r = result_holder["result"]
                st.session_state.agent_session_id      = r.session_id
                st.session_state.total_input_tokens  += r.usage.input_tokens
                st.session_state.total_output_tokens += r.usage.output_tokens
                st.session_state.total_cost          += r.total_cost_usd
                log("info", f"{r.usage.input_tokens} in / {r.usage.output_tokens} out | stop={r.stop_reason}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": r.final_output or "(no output)",
                    "input_tokens":  r.usage.input_tokens,
                    "output_tokens": r.usage.output_tokens,
                    "cost":          r.total_cost_usd,
                    "stop_reason":   r.stop_reason or "",
                })

            st.session_state.status = "idle"
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# TAB: EXPLORER
# ─────────────────────────────────────────────────────────────────────────────
with tab_tree:
    st.markdown("### 📁 Explorer")
    browse = Path(st.session_state.tree_browse_path)

    st.markdown(f'<div class="tree-cwd">📍 {browse}</div>', unsafe_allow_html=True)

    nc = st.columns([1, 1, 1, 3])
    if nc[0].button("⬆️ Up",   key="tree_up",   use_container_width=True):
        p = browse.parent
        if p != browse:
            st.session_state.tree_browse_path = str(p)
            st.rerun()
    if nc[1].button("🏠 Home", key="tree_home", use_container_width=True):
        st.session_state.tree_browse_path = str(Path.home())
        st.rerun()
    if nc[2].button("📌 CWD",  key="tree_set_cwd", use_container_width=True):
        st.session_state.cwd = str(browse)
        log("info", f"CWD → {browse}")
        st.success(f"CWD set to `{browse}`")

    custom_path = nc[3].text_input("Go to path", value="", placeholder="Paste any path…",
                                   key="tree_custom_path", label_visibility="collapsed")
    if custom_path.strip() and Path(custom_path.strip()).exists():
        st.session_state.tree_browse_path = str(Path(custom_path.strip()).resolve())
        st.rerun()

    st.caption(f"Agent CWD: `{st.session_state.cwd}`")
    st.markdown("---")

    if not browse.exists():
        st.error(f"Path does not exist: {browse}")
    else:
        entries = _safe_iterdir(browse)
        dirs  = [e for e in entries if _safe_is_dir(e)  and e.name not in IGNORE_DIRS]
        files = [e for e in entries if _safe_is_file(e)]

        for d in dirs:
            with st.expander(f"📁 {d.name}"):
                hc = st.columns([3, 1, 1])
                hc[0].markdown(f'<span style="font-size:11px;color:#8b949e">{d}</span>', unsafe_allow_html=True)
                if hc[1].button("📌 CWD",  key=f"cwd_top_{d.name}"):
                    st.session_state.cwd = str(d); log("info", f"CWD → {d}"); st.rerun()
                if hc[2].button("🔍 Open", key=f"open_top_{d.name}"):
                    st.session_state.tree_browse_path = str(d); st.rerun()
                _render_tree(d, depth=1)

        if files:
            st.markdown("**Files**")
            for f in files:
                try:
                    sz = f.stat().st_size
                    sz_str = f"{sz/1024:.1f} KB" if sz >= 1024 else f"{sz} B"
                except OSError:
                    sz_str = "?"
                st.markdown(
                    f'<div class="tree-file">{file_icon(f.name)} {f.name} '
                    f'<span style="color:#8b949e;font-size:10px">{sz_str}</span></div>',
                    unsafe_allow_html=True,
                )

# ─────────────────────────────────────────────────────────────────────────────
# TAB: SESSIONS
# ─────────────────────────────────────────────────────────────────────────────
with tab_sessions:
    hc = st.columns([3, 1, 1])
    hc[0].markdown("### 🗂️ Sessions")
    if hc[1].button("🔄 Refresh", key="refresh_sessions", use_container_width=True):
        st.rerun()
    if hc[2].button("🆕 New", key="new_session_btn", use_container_width=True):
        reset_session()
        st.success("New session ready.")

    sessions = list_sessions()
    if not sessions:
        st.info("No saved sessions found.")
    else:
        st.caption(f"{len(sessions)} session(s)")
        scroll = st.container(height=600, border=False)
        with scroll:
            for s in sessions:
                is_active    = s["id"] == st.session_state.agent_session_id
                border_color = "#1f6feb" if is_active else "#30363d"
                active_badge = "🟢 active · " if is_active else ""
                st.markdown(
                    f"""<div style="background:#161b22;border:1px solid {border_color};
                    border-radius:8px;padding:10px 14px;margin:6px 0">
                    <div style="display:flex;justify-content:space-between">
                      <span style="color:#79c0ff;font-family:monospace;font-size:12px">{s['id'][:20]}…</span>
                      <span style="color:#8b949e;font-size:11px" title="{s['mtime_abs']}">🕐 {s['mtime_rel']}</span>
                    </div>
                    <div style="margin:4px 0;font-size:12px;color:#8b949e">
                      {active_badge}🤖 {s['model']} · 💬 {s['total_msgs']} msgs
                      ({s['user_msgs']}↑ {s['asst_msgs']}↓) · 🔄 {s['turns']} turns · 💰 ${s['cost']:.4f}
                    </div>
                    <div style="font-size:12px;color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                      💬 {s['prompt']}
                    </div></div>""",
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2)
                if c1.button("▶️ Resume", key=f"resume_{s['id']}", use_container_width=True):
                    usage = load_usage(s["id"])
                    st.session_state.agent_session_id   = s["id"]
                    st.session_state.messages           = load_messages(s["id"])
                    st.session_state.total_input_tokens  = usage["input_tokens"]
                    st.session_state.total_output_tokens = usage["output_tokens"]
                    st.session_state.total_cost          = usage["total_cost"]
                    log("info", f"Resumed {s['id']}")
                    st.rerun()
                if c2.button("🆕 Fork", key=f"fork_{s['id']}", use_container_width=True):
                    reset_session()
                    log("info", "New session started")
                    st.success("New session started.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: LOGS
# ─────────────────────────────────────────────────────────────────────────────
with tab_logs:
    lc = st.columns([3, 1, 1])
    lc[0].markdown("### 🪵 Logs")
    if lc[1].button("🔄 Refresh", key="refresh_logs", use_container_width=True):
        st.rerun()
    if lc[2].button("🗑️ Clear",   key="clear_logs",   use_container_width=True):
        st.session_state.logs = []
        st.rerun()

    level_filter = st.radio("Filter", ["all", "error", "info"], horizontal=True, key="log_filter")
    logs = st.session_state.logs[::-1]
    if level_filter != "all":
        logs = [l for l in logs if l["level"] == level_filter]

    log_box = st.container(height=600, border=False)
    with log_box:
        if not logs:
            st.info("No logs yet.")
        else:
            for entry in logs:
                css  = "log-error" if entry["level"] == "error" else "log-info"
                icon = "🔴" if entry["level"] == "error" else "⚪"
                text = entry["text"].replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
                st.markdown(
                    f'<div class="log-entry {css}">{icon} <b>{entry["ts"]}</b> {text}</div>',
                    unsafe_allow_html=True,
                )
