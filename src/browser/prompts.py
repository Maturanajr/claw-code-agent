"""
System prompt injection for browser tools.
"""
from __future__ import annotations


def get_browser_guidance_section(browser_enabled: bool = True) -> str:
    if not browser_enabled:
        return ""
    return """
## Browser Automation

You have a real Chromium browser via Playwright. Use it whenever the user asks to open, navigate, or interact with any website.

**You are NOT a text-only assistant when browser tools are enabled. You have a real browser. Use it.**

### Workflow
1. `browser_status` — confirm browser is LIVE. If not, call `browser_open`.
2. `browser_navigate` — go to URL. Read the domain knowledge returned.
3. `browser_recall` — check what you already know about this domain before acting.
4. Interact using the tools below.
5. When something works, call `browser_learn` to save it.

### Error handling and resilience — CRITICAL
When a tool fails (timeout, element not found, selector error), you MUST:
1. **Never give up after one failure.** Always try an alternative.
2. Alternatives to try:
   - Element not found / timeout → call `browser_scroll_to` first (lazy-loaded content)
   - Selector fails → call `browser_try_selectors` with multiple candidates
   - Input not found → use `browser_type` with selector='auto'
   - Page not ready → `browser_wait` then retry
   - Content hidden → `browser_scroll` down then retry
3. **When something works**, call `browser_learn` to save the working approach for this URL/domain.
4. **Before retrying**, think: is this content lazy-loaded? Does it need scrolling first?

### Lazy-loaded content (YouTube comments, Reddit, Twitter feeds, etc.)
These require scrolling before they appear in the DOM:
- Use `browser_scroll_to` with the target selector to scroll until it appears.
- Use `browser_get_lazy_content` to collect multiple items by scrolling.
- YouTube comments: `#content-text` (MUST scroll to load — never use wait with short timeout)
- YouTube title: `h1.ytd-watch-metadata`
- Twitter/X: `[data-testid="tweetText"]`

### Rules
- NEVER say "I cannot open a browser" — use `browser_open`.
- NEVER give up after one failed selector — try alternatives with `browser_try_selectors`.
- ALWAYS save what works with `browser_learn`.
- ALWAYS check `browser_recall` before trying something you may have done before on this domain.
- The session persists cookies/localStorage — you may already be logged in.

### Available tools
browser_open, browser_close, browser_status, browser_navigate,
browser_search (use for searching — not browser_type),
browser_try_selectors (try multiple selectors, saves what works),
browser_learn, browser_recall, browser_knowledge_summary,
browser_screenshot, browser_get_content, browser_find, browser_click,
browser_type (selector='auto' for smart detection), browser_press,
browser_scroll, browser_scroll_to, browser_wait, browser_get_lazy_content,
browser_evaluate, browser_get_cookies, browser_select, browser_hover,
browser_get_attribute, browser_assert
""".strip()
