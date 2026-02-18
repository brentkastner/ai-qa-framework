"""Smart selector resolution — tries multiple strategies to find elements."""

from __future__ import annotations

import logging
import re

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class SelectorResolutionResult:
    """Result of a selector resolution attempt."""

    def __init__(
        self,
        resolved_selector: str | None,
        strategy_used: str,
        attempts: list[dict],
    ):
        self.resolved_selector = resolved_selector
        self.strategy_used = strategy_used
        self.attempts = attempts  # [{strategy, selector, success}]


async def resolve_selector(
    page: Page,
    original_selector: str,
    timeout_ms: int = 10000,
    action_type: str = "",
) -> SelectorResolutionResult:
    """Try to find an element using progressively broader strategies.

    Strategy order:
    1. Original selector with the configured timeout
    2. Alternative selectors derived from the original (short timeouts)
    3. DOM stability wait + retry original

    Returns a SelectorResolutionResult. If resolved_selector is None,
    all strategies failed.
    """
    attempts: list[dict] = []

    # Strategy 1: Original selector with the full configured timeout
    if await _try_selector(page, original_selector, timeout_ms):
        return SelectorResolutionResult(
            resolved_selector=original_selector,
            strategy_used="original",
            attempts=[{"strategy": "original", "selector": original_selector, "success": True}],
        )
    attempts.append({"strategy": "original", "selector": original_selector, "success": False})
    logger.debug("Smart resolve: original selector '%s' not found, trying alternatives", original_selector)

    # Strategy 2: Derive alternative selectors and try each with a short timeout
    alt_timeout_ms = min(2000, timeout_ms // 3)
    alternatives = _derive_alternatives(original_selector, action_type)
    for alt_strategy, alt_selector in alternatives:
        if await _try_selector(page, alt_selector, alt_timeout_ms):
            logger.info(
                "Smart resolve: '%s' -> '%s' via %s",
                original_selector, alt_selector, alt_strategy,
            )
            return SelectorResolutionResult(
                resolved_selector=alt_selector,
                strategy_used=alt_strategy,
                attempts=attempts + [{"strategy": alt_strategy, "selector": alt_selector, "success": True}],
            )
        attempts.append({"strategy": alt_strategy, "selector": alt_selector, "success": False})

    # Strategy 3: Wait for DOM stability then retry original
    stability_timeout = min(2000, timeout_ms // 4)
    try:
        await page.wait_for_load_state("networkidle", timeout=stability_timeout)
    except Exception:
        pass
    if await _try_selector(page, original_selector, alt_timeout_ms):
        logger.info("Smart resolve: '%s' succeeded after DOM stability wait", original_selector)
        return SelectorResolutionResult(
            resolved_selector=original_selector,
            strategy_used="dom_stability_retry",
            attempts=attempts + [{"strategy": "dom_stability_retry", "selector": original_selector, "success": True}],
        )
    attempts.append({"strategy": "dom_stability_retry", "selector": original_selector, "success": False})

    # All strategies exhausted
    logger.debug("Smart resolve: all strategies failed for '%s' (%d attempts)", original_selector, len(attempts))
    return SelectorResolutionResult(
        resolved_selector=None,
        strategy_used="none",
        attempts=attempts,
    )


async def _try_selector(page: Page, selector: str, timeout_ms: int) -> bool:
    """Try to locate an element with the given selector. Returns True if found."""
    try:
        el = await page.wait_for_selector(selector, timeout=timeout_ms, state="attached")
        return el is not None
    except Exception:
        return False


def _derive_alternatives(original_selector: str, action_type: str) -> list[tuple[str, str]]:
    """Derive alternative selectors from the original.

    Returns a list of (strategy_name, selector_string) tuples.
    Only generates alternatives that differ from the original.
    """
    alternatives: list[tuple[str, str]] = []
    seen: set[str] = {original_selector}

    def _add(strategy: str, selector: str) -> None:
        if selector and selector not in seen:
            seen.add(selector)
            alternatives.append((strategy, selector))

    # Extract signals from the original selector
    id_match = re.search(r"#([\w-]+)", original_selector)
    name_match = re.search(r"\[name=['\"]?([\w-]+)['\"]?\]", original_selector)
    placeholder_match = re.search(r"\[placeholder=['\"]?([^'\"]+)['\"]?\]", original_selector)
    aria_label_match = re.search(r"\[aria-label=['\"]?([^'\"]+)['\"]?\]", original_selector)
    text_match = re.search(r"text[=~]*['\"]([^'\"]+)['\"]", original_selector, re.IGNORECASE)
    has_text_match = re.search(r":has-text\(['\"]([^'\"]+)['\"]\)", original_selector)

    # Broaden by ID (drop tag qualifier)
    if id_match:
        _add("id_only", f"#{id_match.group(1)}")

    # Broaden by name attribute (drop tag qualifier)
    if name_match:
        _add("name_attr", f"[name=\"{name_match.group(1)}\"]")

    # Try by placeholder text
    if placeholder_match:
        _add("placeholder", f"[placeholder=\"{placeholder_match.group(1)}\"]")

    # Try by aria-label
    if aria_label_match:
        _add("aria_label", f"[aria-label=\"{aria_label_match.group(1)}\"]")

    # Try Playwright text selector
    if text_match:
        _add("text_selector", f"text={text_match.group(1)}")

    # Try text from :has-text() for click/hover actions
    if has_text_match and action_type in ("click", "hover"):
        _add("has_text", f"text={has_text_match.group(1)}")

    # Relax complex CSS selectors
    relaxed = _relax_css_selector(original_selector)
    if relaxed:
        _add("relaxed_css", relaxed)

    return alternatives


def _relax_css_selector(selector: str) -> str | None:
    """Simplify a complex CSS selector by removing pseudo-classes and deep nesting.

    Returns None if the selector can't be meaningfully relaxed.
    """
    # Skip Playwright-specific selectors (text=, role=, etc.)
    if re.match(r"^(text|role|data-testid)=", selector):
        return None

    relaxed = selector

    # Remove :nth-child, :first-child, :last-child
    relaxed = re.sub(r":nth-child\([^)]+\)", "", relaxed)
    relaxed = re.sub(r":(first|last)-child", "", relaxed)

    # Remove :not(...) pseudo-classes
    relaxed = re.sub(r":not\([^)]+\)", "", relaxed)

    # Remove :has-text(...) pseudo-classes
    relaxed = re.sub(r":has-text\([^)]+\)", "", relaxed)

    # Simplify deeply nested selectors: keep only the last two segments
    parts = relaxed.split()
    if len(parts) > 3:
        relaxed = " ".join(parts[-2:])

    relaxed = relaxed.strip()

    # Only return if we actually simplified something
    if relaxed and relaxed != selector:
        return relaxed
    return None
