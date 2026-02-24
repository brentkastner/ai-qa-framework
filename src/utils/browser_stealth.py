"""Browser stealth utilities — reduces bot detection signals in Playwright."""

from __future__ import annotations

import random
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_STEALTH_INIT_SCRIPT = """
// Hide navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// Fake plugin array (headless Chrome has zero plugins)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ];
        plugins.length = 3;
        return plugins;
    },
});

// Fake languages (headless Chrome can expose empty or minimal list)
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Ensure window.chrome exists with runtime (missing in headless)
if (!window.chrome) {
    window.chrome = {};
}
if (!window.chrome.runtime) {
    window.chrome.runtime = {};
}

// Fix permissions query for notifications (headless returns 'denied' instantly)
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
"""


async def launch_stealth_browser(playwright: Playwright, headless: bool = True) -> Browser:
    """Launch Chromium with anti-detection arguments."""
    return await playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
    )


async def create_stealth_context(
    browser: Browser,
    viewport: dict,
    user_agent: Optional[str] = None,
    storage_state: Optional[dict | str] = None,
    record_video_dir: str | None = None,
) -> BrowserContext:
    """Create a browser context with stealth patches applied.

    Args:
        storage_state: Optional Playwright storage state (cookies + localStorage)
            to seed the context with. Accepts a dict or a path to a JSON file.
        record_video_dir: Optional directory path for Playwright video recording.
            When provided, all pages in this context will be recorded as .webm files.
    """
    context_kwargs: dict = {
        "viewport": viewport,
        "user_agent": user_agent or DEFAULT_USER_AGENT,
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
        },
        "storage_state": storage_state,
    }
    if record_video_dir:
        context_kwargs["record_video_dir"] = record_video_dir
        context_kwargs["record_video_size"] = viewport

    context = await browser.new_context(**context_kwargs)
    await context.add_init_script(_STEALTH_INIT_SCRIPT)
    return context


async def human_delay(page: Page, min_ms: int = 50, max_ms: int = 300) -> None:
    """Wait a randomized amount of time to mimic human interaction pacing."""
    await page.wait_for_timeout(random.randint(min_ms, max_ms))
