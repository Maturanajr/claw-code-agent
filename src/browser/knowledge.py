"""
Domain knowledge store — persists what the agent learns about each website.
Stored in .browser_session/knowledge.json (gitignored).

Structure:
{
  "youtube.com": {
    "search": {
      "method": "url",
      "url_template": "https://www.youtube.com/results?search_query={query}",
      "notes": "URL search is reliable. Input selector times out."
    },
    "login": { ... }
  }
}
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

_STORE_PATH = Path(".browser_session/knowledge.json")


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
