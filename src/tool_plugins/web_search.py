"""
Web search plugin — DuckDuckGo search + URL fetch.
No API key, no browser, pure HTTP.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from ..agent_tools import AgentTool, ToolExecutionContext, ToolExecutionError
from .base import ToolPlugin

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ClawCodeAgent/1.0)",
    "Accept": "application/json",
}
_DDG_API  = "https://api.duckduckgo.com/"
_DDG_HTML = "https://html.duckduckgo.com/html/"


def _h() -> dict:
    return dict(_HEADERS)


def _ddg_instant(query: str, timeout: int = 8) -> dict:
    params = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"})
    req = urllib.request.Request(f"{_DDG_API}?{params}", headers=_h())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _ddg_html(query: str, max_results: int = 5, timeout: int = 10) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "kl": "br-pt"})
    req = urllib.request.Request(_DDG_HTML, headers=_h(), method="POST", data=params.encode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", errors="replace")
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html, re.DOTALL,
    )
    results = []
    for url, title, snippet in blocks[:max_results]:
        title   = re.sub(r"<[^>]+>", "", title).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        if "uddg=" in url:
            m = re.search(r"uddg=([^&]+)", url)
            url = urllib.parse.unquote(m.group(1)) if m else url
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _fetch_url(url: str, max_chars: int = 4000, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=_h())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
    raw  = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s{2,}", "\n", text).strip()
    return text[:max_chars]


# ── handlers ──────────────────────────────────────────────────────────────────

def _web_search(args: dict[str, Any], ctx: ToolExecutionContext) -> tuple[str, dict]:
    query = args.get("query", "").strip()
    if not query:
        raise ToolExecutionError("'query' is required.")
    max_results = int(args.get("max_results", 5))
    lines: list[str] = []
    results: list[dict] = []

    try:
        instant = _ddg_instant(query)
        abstract = instant.get("AbstractText", "").strip()
        if abstract:
            lines += [f"## Instant Answer ({instant.get('AbstractSource', '')})", abstract,
                      f"Source: {instant.get('AbstractURL', '')}", ""]
    except Exception:
        pass

    try:
        results = _ddg_html(query, max_results=max_results)
        if results:
            lines.append(f"## Web Results ({len(results)})")
            for i, r in enumerate(results, 1):
                lines += [f"{i}. {r['title']}", f"   {r['url']}", f"   {r.get('snippet', '')}", ""]
    except Exception as e:
        lines.append(f"(Web results unavailable: {e})")

    if not lines:
        return f"No results found for: {query}", {}
    return "\n".join(lines), {"query": query, "result_count": len(results)}


def _web_fetch(args: dict[str, Any], ctx: ToolExecutionContext) -> tuple[str, dict]:
    url = args.get("url", "").strip()
    if not url:
        raise ToolExecutionError("'url' is required.")
    max_chars = int(args.get("max_chars", 4000))
    try:
        text = _fetch_url(url, max_chars=max_chars)
        return text, {"url": url, "chars": len(text)}
    except Exception as e:
        raise ToolExecutionError(f"Failed to fetch {url}: {e}")


# ── plugin definition ─────────────────────────────────────────────────────────

PLUGIN = ToolPlugin(
    name="web_search",
    enabled=True,  # always active
    tools=[
        AgentTool(
            name="web_search",
            description=(
                "Search the web via DuckDuckGo. Returns instant answers and top results. "
                "NO browser needed — pure HTTP, fast and token-efficient. "
                "PREFER this over the browser for any information lookup."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "description": "Default 5."},
                },
                "required": ["query"],
            },
            handler=_web_search,
        ),
        AgentTool(
            name="web_fetch",
            description=(
                "Fetch a URL and return its plain text. "
                "Use after web_search to read a specific page without the browser."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "description": "Default 4000."},
                },
                "required": ["url"],
            },
            handler=_web_fetch,
        ),
    ],
    prompt=(
        "You have web_search and web_fetch tools.\n"
        "- Use web_search for any information lookup — no browser needed.\n"
        "- Use web_fetch to read a specific URL as plain text.\n"
        "- NEVER fabricate information — search first, answer from results.\n"
        "- Only use the browser when you need to interact with a page."
    ),
)
