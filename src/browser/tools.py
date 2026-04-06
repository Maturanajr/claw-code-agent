"""
Browser tool handlers — async Playwright via BrowserSession.run().
Each function: (arguments: dict, context: ToolExecutionContext) -> str | tuple[str, dict]
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib.parse import quote_plus

from ..agent_tools import ToolExecutionContext, ToolExecutionError
from .config import BrowserConfig
from .session import BrowserSession
from . import knowledge as kb


def _req(args: dict, key: str) -> Any:
    val = args.get(key)
    if val is None:
        raise ToolExecutionError(f"Missing required argument: '{key}'")
    return val

def _session() -> BrowserSession:
    s = BrowserSession.get()
    if s is None or not s.is_alive():
        raise ToolExecutionError("Browser is not open. Call browser_open first.")
    return s


# ── smart input finder ────────────────────────────────────────────────────────
# Ordered list of selectors tried when looking for a search/text input
_SEARCH_SELECTORS = [
    "input[type='search']",
    "input[name='search']",
    "input[name='q']",
    "input[name='query']",
    "input[placeholder*='search' i]",
    "input[placeholder*='buscar' i]",
    "input[placeholder*='pesquisar' i]",
    "input[aria-label*='search' i]",
    "input[aria-label*='buscar' i]",
    "textarea[name='q']",
    "input[type='text']",
    "input:not([type='hidden']):not([type='submit']):not([type='button'])",
]

async def _find_search_input(page):
    """Try multiple selectors to find a search input. Returns locator or None."""
    for sel in _SEARCH_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible():
                return loc, sel
        except Exception:
            continue
    return None, None


# ── tools ─────────────────────────────────────────────────────────────────────

def browser_open(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    headless = bool(args.get("headless", False))
    cfg = BrowserConfig(headless=headless)
    session = BrowserSession.launch(cfg)
    status = session.status()
    return (
        f"Browser {'launched' if status['alive'] else 'failed'}.\n"
        f"URL: {status.get('url', 'about:blank')}\nHeadless: {headless}",
        {"status": status},
    )


def browser_close(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    return BrowserSession.close_global(), {}


def browser_status(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = BrowserSession.get()
    if s is None:
        return "Browser is not open.", {"alive": False}
    status = s.status()
    if status["alive"]:
        return (
            f"Browser is LIVE.\nURL: {status['url']}\nTitle: {status['title']}",
            status,
        )
    return "Browser is NOT alive.", status


def browser_navigate(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    url = _req(args, "url")
    wait_until = args.get("wait_until", "domcontentloaded")
    s = _session()

    async def _go():
        resp = await s._page.goto(url, wait_until=wait_until)
        title = await s._page.title()
        return resp.status if resp else None, title, s._page.url

    code, title, final_url = s.run(_go())

    # attach any known domain knowledge to the response
    known = kb.get_domain_knowledge(final_url)
    knowledge_hint = ""
    if known:
        knowledge_hint = f"\n\n[Domain knowledge for {final_url}]:\n{json.dumps(known, indent=2)}"

    return (
        f"Navigated to: {final_url}\nTitle: {title}\nStatus: {code}{knowledge_hint}",
        {"url": final_url, "title": title, "status_code": code, "domain_knowledge": known},
    )


def browser_search(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """
    Smart search on the current page or via URL.
    Tries known domain knowledge first, then URL search, then DOM input discovery.
    Saves what worked for future use.
    """
    query = _req(args, "query")
    s = _session()
    current_url = s._page.url

    # 1. check stored knowledge for this domain
    known = kb.get_fact(current_url, "search")
    if known and known.get("method") == "url" and known.get("url_template"):
        url = known["url_template"].replace("{query}", quote_plus(query))
        s.run(s._page.goto(url, wait_until="domcontentloaded"))
        title = s.run(s._page.title())
        return (
            f"Searched via known URL method.\nURL: {s._page.url}\nTitle: {title}",
            {"method": "url_known", "url": s._page.url},
        )

    # 2. try URL-based search (most reliable, no DOM interaction needed)
    url_templates = _guess_search_url(current_url, query)
    for url_template, method_name in url_templates:
        try:
            s.run(s._page.goto(url_template, wait_until="domcontentloaded"))
            title = s.run(s._page.title())
            # save this as working method
            kb.set_fact(current_url, "search", {
                "method": "url",
                "url_template": url_template.replace(quote_plus(query), "{query}"),
                "notes": f"URL search works. Discovered automatically.",
            })
            return (
                f"Searched via URL ({method_name}).\nURL: {s._page.url}\nTitle: {title}",
                {"method": method_name, "url": s._page.url},
            )
        except Exception:
            continue

    # 3. fallback: find search input in DOM
    async def _dom_search():
        loc, sel = await _find_search_input(s._page)
        if loc is None:
            raise ToolExecutionError(
                "Could not find a search input. Try browser_navigate with a search URL directly."
            )
        await loc.click()
        await loc.fill("")
        await loc.type(query, delay=60)
        await s._page.keyboard.press("Enter")
        await s._page.wait_for_load_state("domcontentloaded")
        title = await s._page.title()
        return sel, title, s._page.url

    sel, title, final_url = s.run(_dom_search())
    # save DOM method
    kb.set_fact(current_url, "search", {
        "method": "dom",
        "selector": sel,
        "notes": "DOM input search works.",
    })
    return (
        f"Searched via DOM input (selector: {sel}).\nURL: {final_url}\nTitle: {title}",
        {"method": "dom", "selector": sel, "url": final_url},
    )


def _guess_search_url(current_url: str, query: str) -> list[tuple[str, str]]:
    """Return candidate search URLs for known domains."""
    q = quote_plus(query)
    from urllib.parse import urlparse
    host = urlparse(current_url).netloc.lower()

    candidates = []
    if "youtube.com" in host:
        candidates.append((f"https://www.youtube.com/results?search_query={q}", "youtube_url"))
    elif "google.com" in host:
        candidates.append((f"https://www.google.com/search?q={q}", "google_url"))
    elif "github.com" in host:
        candidates.append((f"https://github.com/search?q={q}", "github_url"))
    elif "twitter.com" in host or "x.com" in host:
        candidates.append((f"https://twitter.com/search?q={q}", "twitter_url"))
    elif "reddit.com" in host:
        candidates.append((f"https://www.reddit.com/search/?q={q}", "reddit_url"))
    elif "amazon.com" in host:
        candidates.append((f"https://www.amazon.com/s?k={q}", "amazon_url"))
    elif "wikipedia.org" in host:
        candidates.append((f"https://en.wikipedia.org/w/index.php?search={q}", "wikipedia_url"))
    # generic fallback: try appending ?q= or ?search=
    base = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
    candidates.append((f"{base}/search?q={q}", "generic_search_q"))
    candidates.append((f"{base}/?s={q}", "generic_s"))
    return candidates


def browser_learn(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """
    Store a fact about the current domain for future use.
    E.g. how to search, login, navigate menus, etc.
    """
    s = _session()
    key = _req(args, "key")
    value = _req(args, "value")
    url = s._page.url
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {"notes": value}
    kb.set_fact(url, key, value)
    return (
        f"Learned: [{kb._domain(url)}] {key} = {json.dumps(value)}",
        {"domain": kb._domain(url), "key": key, "value": value},
    )


def browser_recall(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """
    Retrieve stored knowledge about the current domain or a specific URL.
    """
    url = args.get("url")
    if url is None:
        s = _session()
        url = s._page.url
    key = args.get("key")
    if key:
        fact = kb.get_fact(url, key)
        if fact is None:
            return f"No knowledge stored for [{kb._domain(url)}] {key}.", {}
        return f"[{kb._domain(url)}] {key}: {json.dumps(fact, indent=2)}", {"fact": fact}
    known = kb.get_domain_knowledge(url)
    if not known:
        return f"No knowledge stored for {kb._domain(url)}.", {}
    return (
        f"Knowledge for {kb._domain(url)}:\n{json.dumps(known, indent=2)}",
        {"domain": kb._domain(url), "knowledge": known},
    )


def browser_knowledge_summary(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """Show all stored domain knowledge."""
    return kb.all_knowledge_summary(), {}


def browser_screenshot(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    full_page = bool(args.get("full_page", False))
    cfg = s.config

    async def _shot():
        kw: dict = {"type": cfg.screenshot_type, "full_page": full_page}
        if cfg.screenshot_type == "jpeg":
            kw["quality"] = cfg.screenshot_quality
        return await s._page.screenshot(**kw)

    data = s.run(_shot())
    b64 = base64.b64encode(data).decode()
    return (
        f"Screenshot taken ({len(data)} bytes).\nbase64:{b64[:80]}…",
        {"base64": b64, "size": len(data)},
    )


def browser_get_content(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    mode = args.get("mode", "text")
    max_chars = int(args.get("max_chars", 8000))

    async def _get():
        if mode == "html":
            return await s._page.content()
        return await s._page.evaluate("() => document.body.innerText")

    content = s.run(_get())
    truncated = len(content) > max_chars
    return (
        content[:max_chars] + ("\n…[truncated]" if truncated else ""),
        {"url": s._page.url, "mode": mode, "truncated": truncated},
    )


def browser_find(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    selector = args.get("selector")
    text = args.get("text")
    role = args.get("role")

    async def _find():
        results = []
        if selector:
            els = await s._page.query_selector_all(selector)
            for el in els[:20]:
                try:
                    results.append({
                        "tag": await el.evaluate("e => e.tagName.toLowerCase()"),
                        "text": (await el.inner_text())[:100],
                        "visible": await el.is_visible(),
                    })
                except Exception:
                    pass
        elif text:
            for el in (await s._page.get_by_text(text, exact=False).all())[:20]:
                try:
                    results.append({
                        "text": (await el.inner_text())[:100],
                        "visible": await el.is_visible(),
                    })
                except Exception:
                    pass
        elif role:
            for el in (await s._page.get_by_role(role).all())[:20]:
                try:
                    results.append({
                        "role": role,
                        "text": (await el.inner_text())[:100],
                        "visible": await el.is_visible(),
                    })
                except Exception:
                    pass
        else:
            raise ToolExecutionError("Provide 'selector', 'text', or 'role'.")
        return results

    results = s.run(_find())
    return (
        f"Found {len(results)} element(s):\n{json.dumps(results, indent=2)}",
        {"count": len(results), "elements": results},
    )


def browser_click(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    selector = args.get("selector")
    text = args.get("text")

    async def _click():
        if selector:
            await s._page.click(selector)
            return f"Clicked selector: {selector}"
        elif text:
            await s._page.get_by_text(text, exact=False).first.click()
            return f"Clicked element with text: {text}"
        raise ToolExecutionError("Provide 'selector' or 'text'.")

    return s.run(_click()), {}


def browser_type(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """Type into an element. Uses smart input discovery if selector is 'auto'."""
    s = _session()
    selector = args.get("selector", "auto")
    text = _req(args, "text")
    clear_first = bool(args.get("clear_first", True))
    delay = int(args.get("delay_ms", 60))

    async def _type():
        if selector == "auto":
            loc, found_sel = await _find_search_input(s._page)
            if loc is None:
                raise ToolExecutionError("Could not find a text input automatically. Provide a selector.")
            if clear_first:
                await loc.fill("")
            await loc.type(text, delay=delay)
            return f"Typed into auto-detected input ({found_sel}): {text[:50]}"
        else:
            if clear_first:
                await s._page.fill(selector, "")
            await s._page.type(selector, text, delay=delay)
            return f"Typed into '{selector}': {text[:50]}"

    return s.run(_type()), {}


def browser_press(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    key = _req(args, "key")
    selector = args.get("selector")

    async def _press():
        if selector:
            await s._page.press(selector, key)
        else:
            await s._page.keyboard.press(key)

    s.run(_press())
    return f"Pressed key: {key}", {}


def browser_scroll(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    direction = args.get("direction", "down")
    amount = int(args.get("amount", 500))
    dy = amount if direction == "down" else -amount
    s.run(s._page.evaluate(f"window.scrollBy(0, {dy})"))
    return f"Scrolled {direction} by {amount}px", {}


def browser_wait(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    selector = args.get("selector")
    ms = int(args.get("ms", 5000))
    scroll_into_view = bool(args.get("scroll_into_view", False))

    async def _wait():
        if selector:
            # scroll down progressively to trigger lazy loading if needed
            if scroll_into_view:
                for _ in range(5):
                    await s._page.evaluate("window.scrollBy(0, 400)")
                    await s._page.wait_for_timeout(500)
                    el = s._page.locator(selector).first
                    try:
                        if await el.is_visible():
                            await el.scroll_into_view_if_needed()
                            return f"Selector '{selector}' appeared after scroll."
                    except Exception:
                        pass
            await s._page.wait_for_selector(selector, timeout=ms)
            return f"Selector '{selector}' appeared."
        await s._page.wait_for_timeout(ms)
        return f"Waited {ms}ms."

    return s.run(_wait()), {}


def browser_scroll_to(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """
    Scroll until an element is visible (handles lazy-loaded content like YouTube comments).
    Scrolls progressively and waits for the element to appear.
    """
    s = _session()
    selector = _req(args, "selector")
    max_scrolls = int(args.get("max_scrolls", 10))
    scroll_amount = int(args.get("scroll_amount", 600))
    wait_ms = int(args.get("wait_ms", 800))

    async def _scroll_to():
        for i in range(max_scrolls):
            await s._page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await s._page.wait_for_timeout(wait_ms)
            try:
                el = s._page.locator(selector).first
                if await el.is_visible():
                    await el.scroll_into_view_if_needed()
                    return f"Found '{selector}' after {i+1} scroll(s)."
            except Exception:
                pass
        return f"Could not find '{selector}' after {max_scrolls} scrolls."

    return s.run(_scroll_to()), {}


def browser_get_lazy_content(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """
    Scroll down progressively and extract text from a selector that loads lazily.
    Useful for YouTube comments, infinite scroll feeds, etc.
    """
    s = _session()
    selector = _req(args, "selector")
    max_scrolls = int(args.get("max_scrolls", 15))
    scroll_amount = int(args.get("scroll_amount", 500))
    wait_ms = int(args.get("wait_ms", 1000))
    max_items = int(args.get("max_items", 5))

    async def _lazy():
        found = []
        for i in range(max_scrolls):
            await s._page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await s._page.wait_for_timeout(wait_ms)
            els = await s._page.query_selector_all(selector)
            for el in els:
                try:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip()
                        if text and text not in found:
                            found.append(text)
                except Exception:
                    pass
            if len(found) >= max_items:
                break
        return found

    items = s.run(_lazy())
    if not items:
        return f"No items found for '{selector}' after scrolling.", {"items": []}
    result = "\n\n---\n\n".join(f"[{i+1}] {item[:500]}" for i, item in enumerate(items[:max_items]))
    return result, {"count": len(items), "items": items[:max_items]}


def browser_try_selectors(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    """
    Try a list of CSS selectors in order. Returns the first one that finds a visible element.
    Optionally scrolls to trigger lazy loading before each attempt.
    Saves the working selector to domain knowledge under the given action key.
    """
    s = _session()
    selectors = _req(args, "selectors")
    action_key = args.get("action_key", "element")
    scroll_first = bool(args.get("scroll_first", True))
    extract = args.get("extract", "text")  # text | html | attribute
    attribute = args.get("attribute")
    max_scroll_attempts = int(args.get("max_scroll_attempts", 8))
    scroll_amount = int(args.get("scroll_amount", 500))

    if isinstance(selectors, str):
        try:
            selectors = json.loads(selectors)
        except Exception:
            selectors = [s.strip() for s in selectors.split(",")]

    async def _try():
        errors = []
        for sel in selectors:
            # optionally scroll to trigger lazy loading
            if scroll_first:
                for _ in range(max_scroll_attempts):
                    await s._page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                    await s._page.wait_for_timeout(600)
                    try:
                        el = s._page.locator(sel).first
                        if await el.is_visible():
                            break
                    except Exception:
                        pass

            try:
                el = s._page.locator(sel).first
                if not await el.is_visible():
                    errors.append(f"{sel}: not visible")
                    continue

                if extract == "text":
                    content = await el.inner_text()
                elif extract == "html":
                    content = await el.inner_html()
                elif extract == "attribute" and attribute:
                    content = await el.get_attribute(attribute) or ""
                else:
                    content = await el.inner_text()

                return sel, content.strip(), None
            except Exception as e:
                errors.append(f"{sel}: {e}")
                continue

        return None, None, errors

    working_sel, content, errors = s.run(_try())

    if working_sel is None:
        tried = "\n".join(errors or [])
        raise ToolExecutionError(
            f"None of the selectors worked:\n{tried}\n"
            "Try browser_scroll_to first, or use browser_evaluate to inspect the DOM."
        )

    # save working selector to domain knowledge
    kb.set_fact(s._page.url, action_key, {
        "selector": working_sel,
        "extract": extract,
        "notes": f"Working selector discovered automatically.",
    })

    return (
        f"Working selector: {working_sel}\nContent: {content[:500]}",
        {"selector": working_sel, "content": content, "action_key": action_key},
    )


def browser_evaluate(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    script = _req(args, "script")
    result = s.run(s._page.evaluate(script))
    return f"JS result: {json.dumps(result)[:2000]}", {"result": result}


def browser_get_cookies(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    cookies = s.run(s._context.cookies())
    return json.dumps(cookies, indent=2)[:4000], {"count": len(cookies)}


def browser_select(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    selector = _req(args, "selector")
    value = args.get("value")
    label = args.get("label")

    async def _select():
        if value:
            await s._page.select_option(selector, value=value)
            return f"Selected value '{value}' in '{selector}'"
        elif label:
            await s._page.select_option(selector, label=label)
            return f"Selected label '{label}' in '{selector}'"
        raise ToolExecutionError("Provide 'value' or 'label'.")

    return s.run(_select()), {}


def browser_hover(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    selector = _req(args, "selector")
    s.run(s._page.hover(selector))
    return f"Hovered over '{selector}'", {}


def browser_get_attribute(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    selector = _req(args, "selector")
    attribute = _req(args, "attribute")
    value = s.run(s._page.get_attribute(selector, attribute))
    return f"Attribute '{attribute}' = {value}", {"value": value}


def browser_assert(args: dict, ctx: ToolExecutionContext) -> tuple[str, dict]:
    s = _session()
    selector = _req(args, "selector")
    check = args.get("check", "visible")
    expected = args.get("expected_text", "")

    async def _assert():
        el = await s._page.query_selector(selector)
        if el is None:
            return f"FAIL: selector '{selector}' not found.", {"passed": False}
        if check == "exists":
            return f"PASS: '{selector}' exists.", {"passed": True}
        if check == "visible":
            visible = await el.is_visible()
            return f"{'PASS' if visible else 'FAIL'}: visible={visible}", {"passed": visible}
        if check == "text":
            actual = await el.inner_text()
            passed = expected.lower() in actual.lower()
            return (
                f"{'PASS' if passed else 'FAIL'}: expected '{expected}' in '{actual[:100]}'",
                {"passed": passed},
            )
        raise ToolExecutionError(f"Unknown check: {check}")

    return s.run(_assert())
