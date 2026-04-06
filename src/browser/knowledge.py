"""
Domain knowledge store — persists what the agent learns about each website.
Stored in .browser_session/knowledge.json (gitignored).

Also manages browser state persistence (current URL) for session resume.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

_BASE_DIR = Path(".browser_session")
_STORE_PATH = _BASE_DIR / "knowledge.json"
_STATE_PATH = _BASE_DIR / "state.json"


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc
        # strip www.
        return re.sub(r"^www\.", "", host).lower()
    except Exception:
        return url


def load() -> dict:
    if _STORE_PATH.exists():
        try:
            return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save(data: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_domain_knowledge(url: str) -> dict:
    """Return all known facts for the domain of the given URL."""
    return load().get(_domain(url), {})


def set_fact(url: str, key: str, value: dict) -> None:
    """Store a fact about a domain action (e.g. how to search)."""
    data = load()
    domain = _domain(url)
    if domain not in data:
        data[domain] = {}
    data[domain][key] = value
    save(data)


def get_fact(url: str, key: str) -> dict | None:
    """Retrieve a stored fact for a domain action."""
    return load().get(_domain(url), {}).get(key)


def all_knowledge_summary() -> str:
    """Return a human-readable summary of all stored domain knowledge."""
    data = load()
    if not data:
        return "No domain knowledge stored yet."
    lines = []
    for domain, facts in data.items():
        lines.append(f"\n### {domain}")
        for key, val in facts.items():
            lines.append(f"  {key}: {json.dumps(val)}")
    return "\n".join(lines)


# ── browser state (current URL for session resume) ────────────────────────────

def save_browser_state(url: str, session_id: str | None = None) -> None:
    """Persist the current browser URL so it can be restored on resume."""
    _BASE_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(
        json.dumps({"url": url, "session_id": session_id}, indent=2),
        encoding="utf-8",
    )


def load_browser_state() -> dict:
    """Return the last saved browser state, or empty dict."""
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def clear_browser_state() -> None:
    if _STATE_PATH.exists():
        _STATE_PATH.unlink()
