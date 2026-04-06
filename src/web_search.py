"""
web_search tool — lightweight HTTP search via DuckDuckGo Instant Answer API.

No API key required. Returns clean text results, no browser needed.
Much cheaper in tokens than browser-based search.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .agent_tools import AgentTool, ToolExecutionContext, ToolExecutionError


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ClawCodeAgent/1.0)",
    "Accept": "application/json",
}

_DDG_API = "https://api.duckduckgo.com/"
_DDG_HTML = "https://html.duckduckgo.com/html/"


def _ddg_instant(query: str, timeout: int = 8) -> dict:
    """DuckDuckGo Instant Answer API — returns structured data for known entities."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    })
    req = urllib.request.Request(f"{_DDG_API}?{params}", headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ddg_html_results(query: str, max_results: int = 5, timeout: int = 10) -> list[dict]:
    """
    Scrape DuckDuckGo HTML search results.
    Returns list of {title, url, snippet}.
    """
    params = urllib.parse.urlencode({"q": query, "kl": "br-pt"})
    req = urllib.request.Request(
        f"{_DDG_HTML}?{params}",
        headers=_headers(),
        method="POST",
        data=params.encode(),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    results = []
    # simple regex-free parser — extract result blocks
    import re
    # DuckDuckGo HTML result pattern
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )
    for url, title, snippet in blocks[:max_results]:
        title   = re.sub(r"<[^>]+>", "", title).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        # DDG wraps URLs — extract real URL
        if "uddg=" in url:
            url = urllib.parse.unquote(re.search(r"uddg=([^&]+)", url).group(1))
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _headers() -> dict:
    return dict(_HEADERS)


def _fetch_url(url: str, max_chars: int = 4000, timeout: int = 10) -> str:
    """Fetch a URL and return plain text (strips HTML tags)."""
    import re
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    # strip scripts/styles
    raw = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # strip all tags
    text = re.sub(r"<[^>]+>", " ", raw)
    # collapse whitespace
    text = re.sub(r"\s{2,}", "\n", text).strip()
    return text[:max_chars]


# ── tool handlers ─────────────────────────────────────────────────────────────

def _web_search(arguments: dict[str, Any], context: ToolExecutionContext) -> tuple[str, dict]:
    """
    Search the web via DuckDuckGo. Returns instant answer + top results.
    No browser needed. Much faster and cheaper than browser-based search.
    """
    query = arguments.get("query", "").strip()
    if not query:
        raise ToolExecutionError("'query' is required.")

    max_results = int(arguments.get("max_results", 5))
    lines: list[str] = []

    # 1. instant answer (Wikipedia abstract, definitions, etc.)
    try:
        instant = _ddg_instant(query)
        abstract = instant.get("AbstractText", "").strip()
        if abstract:
            source = instant.get("AbstractSource", "")
            source_url = instant.get("AbstractURL", "")
            lines.append(f"## Instant Answer ({source})")
            lines.append(abstract)
            if source_url:
                lines.append(f"Source: {source_url}")
            lines.append("")
    except Exception:
        pass

    # 2. web results
    try:
        results = _ddg_html_results(query, max_results=max_results)
        if results:
            lines.append(f"## Web Results ({len(results)} found)")
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. **{r['title']}**")
                lines.append(f"   {r['url']}")
                if r.get("snippet"):
                    lines.append(f"   {r['snippet']}")
            lines.append("")
    except Exception as e:
        lines.append(f"(Web results unavailable: {e})")

    if not lines:
        return f"No results found for: {query}", {}

    output = "\n".join(lines)
    return output, {"query": query, "result_count": len(results) if "results" in dir() else 0}


def _web_fetch(arguments: dict[str, Any], context: ToolExecutionContext) -> tuple[str, dict]:
    """
    Fetch a URL and return its plain text content.
    Use after web_search to read a specific page without opening the browser.
    """
    url = arguments.get("url", "").strip()
    if not url:
        raise ToolExecutionError("'url' is required.")
    max_chars = int(arguments.get("max_chars", 4000))
    try:
        text = _fetch_url(url, max_chars=max_chars)
        return text, {"url": url, "chars": len(text)}
    except Exception as e:
        raise ToolExecutionError(f"Failed to fetch {url}: {e}")


# ── tool definitions ──────────────────────────────────────────────────────────

WEB_SEARCH_TOOL = AgentTool(
    name="web_search",
    description=(
        "Search the web via DuckDuckGo. Returns instant answers and top results. "
        "NO browser needed — pure HTTP request, fast and token-efficient. "
        "USE THIS instead of the browser whenever you need to look up information online. "
        "Only use the browser when you need to interact with a page (click, fill forms, etc.)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Max web results to return. Default 5.",
            },
        },
        "required": ["query"],
    },
    handler=_web_search,
)

WEB_FETCH_TOOL = AgentTool(
    name="web_fetch",
    description=(
        "Fetch a URL and return its plain text content. "
        "Use after web_search to read a specific page without opening the browser. "
        "Much faster and cheaper than browser navigation for reading content."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to fetch",
            },
            "max_chars": {
                "type": "integer",
                "description": "Max characters to return. Default 4000.",
            },
        },
        "required": ["url"],
    },
    handler=_web_fetch,
)
