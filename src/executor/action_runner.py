"""Action runner — translates Action models to Playwright calls."""

from __future__ import annotations

import logging
import re
import time

from playwright.async_api import Page

from src.models.test_plan import Action
from src.utils.browser_stealth import human_delay
from .selector_resolver import resolve_selector

logger = logging.getLogger(__name__)

# Dynamic variables that can appear in action values (Postman-style).
_DYNAMIC_VAR_RE = re.compile(r"\{\{\$(\w+)\}\}")


def _build_dynamic_vars() -> dict[str, str]:
    """Build a snapshot of dynamic variable values (fixed for one test case)."""
    return {
        "timestamp": str(int(time.time())),
    }


def _resolve_dynamic_vars(value: str, resolved: dict[str, str]) -> str:
    """Replace ``{{$variable}}`` tokens with pre-computed values."""
    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        if name in resolved:
            return resolved[name]
        logger.warning("Unknown dynamic variable: {{$%s}}", name)
        return match.group(0)

    return _DYNAMIC_VAR_RE.sub(_replacer, value)


def resolve_dynamic_vars_for_test_case(actions: list[Action]) -> None:
    """Resolve all ``{{$variable}}`` tokens in a list of actions in-place.

    A single snapshot of dynamic values is used so that the same
    ``{{$timestamp}}`` value appears in every action (e.g. a vault
    created in preconditions and referenced again in test steps).
    """
    resolved = _build_dynamic_vars()
    for action in actions:
        if action.value and _DYNAMIC_VAR_RE.search(action.value):
            action.value = _resolve_dynamic_vars(action.value, resolved)


async def _resolve_effective_selector(
    page: Page,
    selector: str,
    timeout_ms: int,
    action_type: str,
    smart_resolve: bool,
) -> str:
    """Resolve the effective selector using smart resolution if enabled.

    Returns the resolved selector (possibly an alternative) or the original
    selector if resolution is disabled or all strategies fail.
    """
    if not smart_resolve:
        return selector
    result = await resolve_selector(page, selector, timeout_ms=timeout_ms, action_type=action_type)
    if result.resolved_selector:
        if result.strategy_used != "original":
            logger.info("Smart resolve: '%s' -> '%s' via %s",
                        selector, result.resolved_selector, result.strategy_used)
        return result.resolved_selector
    # All strategies failed — return original so Playwright raises its normal error
    return selector


async def run_action(
    page: Page, action: Action, timeout: int = 10000, smart_resolve: bool = True,
) -> None:
    """Execute a single action on the Playwright page.

    Args:
        page: Playwright page instance.
        action: The action to execute.
        timeout: Selector timeout in milliseconds (default 10000).
        smart_resolve: When True, try alternative selectors before failing.
    """

    logger.debug("Running action: %s | selector=%s | value=%s | %s",
                 action.action_type, action.selector, action.value,
                 action.description or "")

    match action.action_type:
        case "navigate":
            url = action.value or action.selector or ""
            logger.debug("Navigating to %s...", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                logger.debug("Waiting for network idle...")
                await page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
            except Exception:
                logger.debug("Network idle timeout, continuing")

        case "click":
            if not action.selector:
                raise ValueError("click action requires a selector")
            await human_delay(page, min_ms=50, max_ms=250)
            effective = await _resolve_effective_selector(
                page, action.selector, timeout, "click", smart_resolve)
            logger.debug("Clicking: %s", effective)
            await page.click(effective, timeout=timeout)

        case "fill":
            if not action.selector:
                raise ValueError("fill action requires a selector")
            await human_delay(page, min_ms=80, max_ms=300)
            effective = await _resolve_effective_selector(
                page, action.selector, timeout, "fill", smart_resolve)
            logger.debug("Filling %s with '%s'", effective,
                         "***" if "password" in (action.selector or "").lower() else action.value)
            await page.fill(effective, action.value or "", timeout=timeout)

        case "select":
            if not action.selector:
                raise ValueError("select action requires a selector")
            await human_delay(page, min_ms=50, max_ms=250)
            effective = await _resolve_effective_selector(
                page, action.selector, timeout, "select", smart_resolve)
            logger.debug("Selecting '%s' in %s", action.value, effective)
            await page.select_option(effective, action.value or "", timeout=timeout)

        case "hover":
            if not action.selector:
                raise ValueError("hover action requires a selector")
            await human_delay(page, min_ms=30, max_ms=150)
            effective = await _resolve_effective_selector(
                page, action.selector, timeout, "hover", smart_resolve)
            logger.debug("Hovering over: %s", effective)
            await page.hover(effective, timeout=timeout)

        case "scroll":
            if action.value:
                logger.debug("Scrolling to y=%s", action.value)
                await page.evaluate(f"window.scrollTo(0, {action.value})")
            elif action.selector:
                logger.debug("Scrolling element into view: %s", action.selector)
                await page.evaluate(
                    f"document.querySelector('{action.selector}')?.scrollIntoView()"
                )
            else:
                logger.debug("Scrolling to bottom of page")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        case "wait":
            if action.selector:
                effective = await _resolve_effective_selector(
                    page, action.selector, timeout, "wait", smart_resolve)
                logger.debug("Waiting for selector: %s", effective)
                await page.wait_for_selector(effective, timeout=timeout)
            elif action.value:
                logger.debug("Waiting %sms...", action.value)
                await page.wait_for_timeout(int(action.value))
            else:
                logger.debug("Waiting 1000ms...")
                await page.wait_for_timeout(1000)

        case "screenshot":
            logger.debug("Screenshot action (handled by evidence collector)")
            # Screenshots are handled by evidence collector; this is a no-op placeholder
            pass

        case "keyboard":
            key = action.value or "Enter"
            logger.debug("Pressing key: %s", key)
            await page.keyboard.press(key)

        case _:
            logger.warning("Unknown action type: %s", action.action_type)
