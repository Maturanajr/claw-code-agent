from __future__ import annotations

import json
import time
from pathlib import Path

SESSIONS_DIR = Path(".port_sessions/agent")


def relative_time(mtime: float) -> str:
    diff = time.time() - mtime
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff / 60)}m ago"
    if diff < 86400:
        return f"{int(diff / 3600)}h ago"
    if diff < 86400 * 7:
        return f"{int(diff / 86400)}d ago"
    return time.strftime("%b %d, %Y", time.localtime(mtime))


def list_sessions() -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    try:
        from src.browser.knowledge import load_browser_state
        browser_state = load_browser_state()
    except Exception:
        browser_state = {}

    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            msgs = data.get("messages", [])
            user_msgs = sum(
                1 for m in msgs
                if m.get("role") == "user"
                and not str(m.get("content", "")).strip().startswith("<system-reminder>")
            )
            asst_msgs = sum(1 for m in msgs if m.get("role") == "assistant")
            first_user = next(
                (str(m.get("content", ""))[:80] for m in msgs
                 if m.get("role") == "user"
                 and not str(m.get("content", "")).strip().startswith("<system-reminder>")),
                "",
            )
            mtime = f.stat().st_mtime
            browser_url = (
                browser_state.get("url")
                if browser_state.get("session_id") == f.stem
                else None
            )
            sessions.append({
                "id":          f.stem,
                "turns":       data.get("turns", "?"),
                "model":       data.get("model_config", {}).get("model", "?"),
                "mtime":       mtime,
                "mtime_rel":   relative_time(mtime),
                "mtime_abs":   time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
                "user_msgs":   user_msgs,
                "asst_msgs":   asst_msgs,
                "total_msgs":  user_msgs + asst_msgs,
                "prompt":      first_user,
                "cost":        data.get("total_cost_usd", 0.0),
                "browser_url": browser_url,
            })
        except Exception:
            pass
    return sessions


def load_usage(session_id: str) -> dict:
    try:
        data = json.loads((SESSIONS_DIR / f"{session_id}.json").read_text(encoding="utf-8"))
        usage = data.get("usage", {})
        return {
            "input_tokens":  usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_cost":    data.get("total_cost_usd", 0.0),
        }
    except Exception:
        return {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0}


def load_messages(session_id: str) -> list[dict]:
    try:
        data = json.loads((SESSIONS_DIR / f"{session_id}.json").read_text(encoding="utf-8"))
        chat: list[dict] = []
        for m in data.get("messages", []):
            role = m.get("role", "")
            content = m.get("content", "")
            if not content or role == "system":
                continue
            if isinstance(content, list):
                text = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                text = str(content)
            if not text.strip():
                continue
            if role == "user":
                if text.strip().startswith("<system-reminder>"):
                    continue
                chat.append({"role": "user", "content": text})
            elif role == "assistant":
                chat.append({
                    "role": "assistant", "content": text,
                    "input_tokens": None, "output_tokens": None,
                    "cost": 0.0, "stop_reason": "",
                })
        return chat
    except Exception:
        return []
