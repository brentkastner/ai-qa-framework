"""Action runner — translates Action models to Playwright calls."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from src.models.test_plan import Action

logger = logging.getLogger(__name__)


async def run_action(page: Page, action: Action, timeout: int = 30000) -> None:
    """Execute a single action on the Playwright page."""
    logger.debug("Running action: %s selector=%s value=%s",
                 action.action_type, action.selector, action.value)

    match action.action_type:
        case "navigate":
            url = action.value or action.selector or ""
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
            except Exception:
                pass

        case "click":
            if not action.selector:
                raise ValueError("click action requires a selector")
            await page.click(action.selector, timeout=timeout)

        case "fill":
            if not action.selector:
                raise ValueError("fill action requires a selector")
            await page.fill(action.selector, action.value or "", timeout=timeout)

        case "select":
            if not action.selector:
                raise ValueError("select action requires a selector")
            await page.select_option(action.selector, action.value or "", timeout=timeout)

        case "hover":
            if not action.selector:
                raise ValueError("hover action requires a selector")
            await page.hover(action.selector, timeout=timeout)

        case "scroll":
            if action.value:
                await page.evaluate(f"window.scrollTo(0, {action.value})")
            elif action.selector:
                await page.evaluate(
                    f"document.querySelector('{action.selector}')?.scrollIntoView()"
                )
            else:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        case "wait":
            if action.selector:
                await page.wait_for_selector(action.selector, timeout=timeout)
            elif action.value:
                await page.wait_for_timeout(int(action.value))
            else:
                await page.wait_for_timeout(1000)

        case "screenshot":
            # Screenshots are handled by evidence collector; this is a no-op placeholder
            pass

        case "keyboard":
            key = action.value or "Enter"
            await page.keyboard.press(key)

        case _:
            logger.warning("Unknown action type: %s", action.action_type)
