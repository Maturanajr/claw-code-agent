"""
browser_tool_registry() — returns dict[str, AgentTool] following the same
pattern as default_tool_registry() in src/agent_tools.py.
"""
from __future__ import annotations

from ..agent_tools import AgentTool
from . import tools as _t


def browser_tool_registry() -> dict[str, AgentTool]:
    return {t.name: t for t in [

        AgentTool(
            name="browser_open",
            description="Launch a persistent Chromium browser. Call before any other browser tool.",
            parameters={
                "type": "object",
                "properties": {
                    "headless": {"type": "boolean", "description": "Run without visible window. Default false."},
                },
            },
            handler=_t.browser_open,
        ),

        AgentTool(
            name="browser_close",
            description="Close the browser and release all resources.",
            parameters={"type": "object", "properties": {}},
            handler=_t.browser_close,
        ),

        AgentTool(
            name="browser_status",
            description="Check if browser is LIVE. Returns current URL and title. Call before any action.",
            parameters={"type": "object", "properties": {}},
            handler=_t.browser_status,
        ),

        AgentTool(
            name="browser_navigate",
            description="Navigate to a URL. Also returns any stored domain knowledge for that site.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                    },
                },
                "required": ["url"],
            },
            handler=_t.browser_navigate,
        ),

        AgentTool(
            name="browser_search",
            description=(
                "Smart search on the current page. "
                "Tries stored domain knowledge first, then URL-based search, then DOM input discovery. "
                "Saves what works for future use. PREFER this over browser_type for searching."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
            handler=_t.browser_search,
        ),

        AgentTool(
            name="browser_learn",
            description=(
                "Store a fact about the current domain for future use. "
                "E.g. how to search, login, navigate. "
                "Call this whenever you discover something that works on a site."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Fact name, e.g. 'search', 'login', 'menu'"},
                    "value": {
                        "type": "string",
                        "description": "JSON string or plain text describing what works",
                    },
                },
                "required": ["key", "value"],
            },
            handler=_t.browser_learn,
        ),

        AgentTool(
            name="browser_recall",
            description="Retrieve stored knowledge about the current domain or a specific URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to look up (defaults to current page)"},
                    "key": {"type": "string", "description": "Specific fact key (optional)"},
                },
            },
            handler=_t.browser_recall,
        ),

        AgentTool(
            name="browser_try_selectors",
            description=(
                "Try multiple CSS selectors in order and return the first that finds a visible element. "
                "Automatically scrolls to trigger lazy loading. "
                "Saves the working selector to domain knowledge. "
                "Use this whenever a selector fails — provide several alternatives."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selectors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of CSS selectors to try in order.",
                    },
                    "action_key": {
                        "type": "string",
                        "description": "Name for this action in domain knowledge (e.g. 'first_comment', 'search_input'). Default: 'element'",
                    },
                    "scroll_first": {
                        "type": "boolean",
                        "description": "Scroll down before each attempt to trigger lazy loading. Default true.",
                    },
                    "extract": {
                        "type": "string",
                        "enum": ["text", "html", "attribute"],
                        "description": "What to extract from the found element. Default: text",
                    },
                    "attribute": {
                        "type": "string",
                        "description": "Attribute name when extract=attribute.",
                    },
                    "max_scroll_attempts": {
                        "type": "integer",
                        "description": "Max scroll steps per selector. Default 8.",
                    },
                },
                "required": ["selectors"],
            },
            handler=_t.browser_try_selectors,
        ),

        AgentTool(
            name="browser_knowledge_summary",
            description="Show all stored domain knowledge across all sites.",
            parameters={"type": "object", "properties": {}},
            handler=_t.browser_knowledge_summary,
        ),

        AgentTool(
            name="browser_screenshot",
            description="Take a screenshot of the current page.",
            parameters={
                "type": "object",
                "properties": {
                    "full_page": {"type": "boolean"},
                },
            },
            handler=_t.browser_screenshot,
        ),

        AgentTool(
            name="browser_get_content",
            description="Get visible text or HTML of the current page.",
            parameters={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["text", "html"]},
                    "max_chars": {"type": "integer"},
                },
            },
            handler=_t.browser_get_content,
        ),

        AgentTool(
            name="browser_find",
            description="Find elements by CSS selector, visible text, or ARIA role.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                    "role": {"type": "string"},
                },
            },
            handler=_t.browser_find,
        ),

        AgentTool(
            name="browser_click",
            description="Click an element by CSS selector or visible text.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
            handler=_t.browser_click,
        ),

        AgentTool(
            name="browser_type",
            description=(
                "Type text into an input. Use selector='auto' to auto-detect the input field. "
                "For searching, prefer browser_search instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector or 'auto'"},
                    "text": {"type": "string"},
                    "clear_first": {"type": "boolean"},
                    "delay_ms": {"type": "integer"},
                },
                "required": ["text"],
            },
            handler=_t.browser_type,
        ),

        AgentTool(
            name="browser_press",
            description="Press a keyboard key (Enter, Tab, Escape, ArrowDown, etc.).",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "selector": {"type": "string"},
                },
                "required": ["key"],
            },
            handler=_t.browser_press,
        ),

        AgentTool(
            name="browser_scroll",
            description="Scroll the page up or down.",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer"},
                },
            },
            handler=_t.browser_scroll,
        ),

        AgentTool(
            name="browser_wait",
            description=(
                "Wait for a CSS selector to appear, or pause N milliseconds. "
                "Set scroll_into_view=true to scroll progressively until the element appears "
                "(use this for lazy-loaded content like YouTube comments)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "ms": {"type": "integer", "description": "Timeout ms. Default 5000."},
                    "scroll_into_view": {
                        "type": "boolean",
                        "description": "Scroll down until element appears. Default false.",
                    },
                },
            },
            handler=_t.browser_wait,
        ),

        AgentTool(
            name="browser_scroll_to",
            description=(
                "Scroll the page progressively until a CSS selector becomes visible. "
                "Essential for lazy-loaded content (YouTube comments, infinite feeds). "
                "Use this instead of browser_wait when content needs scrolling to load."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to scroll to"},
                    "max_scrolls": {"type": "integer", "description": "Max scroll attempts. Default 10."},
                    "scroll_amount": {"type": "integer", "description": "Pixels per scroll. Default 600."},
                    "wait_ms": {"type": "integer", "description": "Wait between scrolls ms. Default 800."},
                },
                "required": ["selector"],
            },
            handler=_t.browser_scroll_to,
        ),

        AgentTool(
            name="browser_get_lazy_content",
            description=(
                "Scroll down and collect text from elements that load lazily. "
                "Perfect for YouTube comments, Reddit posts, Twitter feeds, etc. "
                "Scrolls progressively and returns up to max_items unique text blocks."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": (
                            "CSS selector for the items to collect. "
                            "YouTube comments: '#content-text', "
                            "Reddit posts: '.Post', "
                            "Twitter: '[data-testid=\"tweetText\"]'"
                        ),
                    },
                    "max_scrolls": {"type": "integer", "description": "Max scroll attempts. Default 15."},
                    "scroll_amount": {"type": "integer", "description": "Pixels per scroll. Default 500."},
                    "wait_ms": {"type": "integer", "description": "Wait between scrolls ms. Default 1000."},
                    "max_items": {"type": "integer", "description": "Max items to return. Default 5."},
                },
                "required": ["selector"],
            },
            handler=_t.browser_get_lazy_content,
        ),

        AgentTool(
            name="browser_evaluate",
            description="Execute JavaScript in the page and return the result.",
            parameters={
                "type": "object",
                "properties": {
                    "script": {"type": "string"},
                },
                "required": ["script"],
            },
            handler=_t.browser_evaluate,
        ),

        AgentTool(
            name="browser_get_cookies",
            description="Return all cookies for the current browser session.",
            parameters={"type": "object", "properties": {}},
            handler=_t.browser_get_cookies,
        ),

        AgentTool(
            name="browser_select",
            description="Select an option in a <select> dropdown.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["selector"],
            },
            handler=_t.browser_select,
        ),

        AgentTool(
            name="browser_hover",
            description="Hover the mouse over an element.",
            parameters={
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
            handler=_t.browser_hover,
        ),

        AgentTool(
            name="browser_get_attribute",
            description="Get an HTML attribute value from an element.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "attribute": {"type": "string"},
                },
                "required": ["selector", "attribute"],
            },
            handler=_t.browser_get_attribute,
        ),

        AgentTool(
            name="browser_assert",
            description="Assert element exists, is visible, or contains text. For testing.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "check": {"type": "string", "enum": ["exists", "visible", "text"]},
                    "expected_text": {"type": "string"},
                },
                "required": ["selector"],
            },
            handler=_t.browser_assert,
        ),

    ]}
    return {t.name: t for t in [

        AgentTool(
            name="browser_open",
            description=(
                "Launch a persistent Chromium browser session. "
                "Keeps cookies and localStorage across runs. "
                "Call this before any other browser tool."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "headless": {
                        "type": "boolean",
                        "description": "Run without visible window. Default false.",
                    },
                },
            },
            handler=_t.browser_open,
        ),

        AgentTool(
            name="browser_close",
            description="Close the browser and release all resources.",
            parameters={"type": "object", "properties": {}},
            handler=_t.browser_close,
        ),

        AgentTool(
            name="browser_status",
            description=(
                "Check if the browser is LIVE. Returns current URL and title. "
                "Always call this before performing browser actions."
            ),
            parameters={"type": "object", "properties": {}},
            handler=_t.browser_status,
        ),

        AgentTool(
            name="browser_navigate",
            description="Navigate to a URL in the browser.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL including https://"},
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "description": "When to consider navigation done. Default: domcontentloaded",
                    },
                },
                "required": ["url"],
            },
            handler=_t.browser_navigate,
        ),

        AgentTool(
            name="browser_screenshot",
            description="Take a screenshot of the current page.",
            parameters={
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full scrollable page. Default false.",
                    },
                },
            },
            handler=_t.browser_screenshot,
        ),

        AgentTool(
            name="browser_get_content",
            description="Get the visible text or HTML of the current page.",
            parameters={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["text", "html"],
                        "description": "text (default) or html",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Max characters to return. Default 8000.",
                    },
                },
            },
            handler=_t.browser_get_content,
        ),

        AgentTool(
            name="browser_find",
            description=(
                "Find elements on the page by CSS selector, visible text, or ARIA role. "
                "Returns up to 20 matches with tag, text, and visibility."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                    "text": {"type": "string", "description": "Visible text to search for"},
                    "role": {
                        "type": "string",
                        "description": "ARIA role (button, link, input, heading, etc.)",
                    },
                },
            },
            handler=_t.browser_find,
        ),

        AgentTool(
            name="browser_click",
            description="Click an element by CSS selector or visible text.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                    "text": {"type": "string", "description": "Visible text of element to click"},
                },
            },
            handler=_t.browser_click,
        ),

        AgentTool(
            name="browser_type",
            description="Type text into an input field with human-like delay.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of input"},
                    "text": {"type": "string", "description": "Text to type"},
                    "clear_first": {
                        "type": "boolean",
                        "description": "Clear field before typing. Default true.",
                    },
                    "delay_ms": {
                        "type": "integer",
                        "description": "Delay between keystrokes in ms. Default 60.",
                    },
                },
                "required": ["selector", "text"],
            },
            handler=_t.browser_type,
        ),

        AgentTool(
            name="browser_press",
            description="Press a keyboard key (Enter, Tab, Escape, ArrowDown, etc.).",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name e.g. Enter, Tab, Escape"},
                    "selector": {
                        "type": "string",
                        "description": "Focus this element first (optional)",
                    },
                },
                "required": ["key"],
            },
            handler=_t.browser_press,
        ),

        AgentTool(
            name="browser_scroll",
            description="Scroll the page up or down.",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Scroll direction. Default down.",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Pixels to scroll. Default 500.",
                    },
                },
            },
            handler=_t.browser_scroll,
        ),

        AgentTool(
            name="browser_wait",
            description="Wait for a CSS selector to appear, or pause for N milliseconds.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Wait for this selector"},
                    "ms": {"type": "integer", "description": "Milliseconds to wait. Default 1000."},
                },
            },
            handler=_t.browser_wait,
        ),

        AgentTool(
            name="browser_evaluate",
            description="Execute JavaScript in the page and return the result.",
            parameters={
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "JS expression or function body. E.g. 'document.title'",
                    },
                },
                "required": ["script"],
            },
            handler=_t.browser_evaluate,
        ),

        AgentTool(
            name="browser_get_cookies",
            description="Return all cookies for the current browser session.",
            parameters={"type": "object", "properties": {}},
            handler=_t.browser_get_cookies,
        ),

        AgentTool(
            name="browser_select",
            description="Select an option in a <select> dropdown.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of <select>"},
                    "value": {"type": "string", "description": "Option value attribute"},
                    "label": {"type": "string", "description": "Option visible label"},
                },
                "required": ["selector"],
            },
            handler=_t.browser_select,
        ),

        AgentTool(
            name="browser_hover",
            description="Hover the mouse over an element (triggers hover states/menus).",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                },
                "required": ["selector"],
            },
            handler=_t.browser_hover,
        ),

        AgentTool(
            name="browser_get_attribute",
            description="Get the value of an HTML attribute from an element.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "attribute": {"type": "string", "description": "e.g. href, src, value, class"},
                },
                "required": ["selector", "attribute"],
            },
            handler=_t.browser_get_attribute,
        ),

        AgentTool(
            name="browser_assert",
            description=(
                "Assert that an element exists, is visible, or contains expected text. "
                "Useful for testing and verification."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                    "check": {
                        "type": "string",
                        "enum": ["exists", "visible", "text"],
                        "description": "What to check. Default: visible",
                    },
                    "expected_text": {
                        "type": "string",
                        "description": "Text to look for (only for check=text)",
                    },
                },
                "required": ["selector"],
            },
            handler=_t.browser_assert,
        ),

    ]}
