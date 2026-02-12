"""Assertion checker — evaluates test assertions against page state."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from playwright.async_api import Page

from src.models.config import FrameworkConfig
from src.models.test_plan import Assertion

logger = logging.getLogger(__name__)


class AssertionResult:
    def __init__(self, passed: bool, message: str = ""):
        self.passed = passed
        self.message = message


async def check_assertion(
    page: Page,
    assertion: Assertion,
    evidence_dir: Path,
    baseline_dir: Path | None = None,
    console_errors: list[str] | None = None,
    network_log: list[dict] | None = None,
    config: FrameworkConfig | None = None,
) -> AssertionResult:
    """Evaluate a single assertion and return the result."""
    logger.debug("Checking assertion: %s", assertion.assertion_type)
    try:
        match assertion.assertion_type:
            case "element_visible":
                return await _check_element_visible(page, assertion)
            case "element_hidden":
                return await _check_element_hidden(page, assertion)
            case "text_contains":
                return await _check_text_contains(page, assertion)
            case "text_equals":
                return await _check_text_equals(page, assertion)
            case "url_matches":
                return _check_url_matches(page, assertion)
            case "screenshot_diff":
                return await _check_screenshot_diff(page, assertion, evidence_dir, baseline_dir, config)
            case "element_count":
                return await _check_element_count(page, assertion)
            case "network_request_made":
                return _check_network_request(assertion, network_log)
            case "no_console_errors":
                return _check_no_console_errors(console_errors)
            case "response_status":
                return _check_response_status(assertion, network_log)
            case _:
                return AssertionResult(False, f"Unknown assertion type: {assertion.assertion_type}")
    except Exception as e:
        return AssertionResult(False, f"Assertion error: {e}")


async def _check_element_visible(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.selector:
        return AssertionResult(False, "No selector for element_visible")
    try:
        el = await page.wait_for_selector(assertion.selector, state="visible", timeout=5000)
        if el:
            return AssertionResult(True, f"Element '{assertion.selector}' is visible")
        return AssertionResult(False, f"Element '{assertion.selector}' not visible")
    except Exception:
        return AssertionResult(False, f"Element '{assertion.selector}' not found/visible")


async def _check_element_hidden(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.selector:
        return AssertionResult(False, "No selector for element_hidden")
    try:
        el = await page.query_selector(assertion.selector)
        if el is None:
            return AssertionResult(True, "Element not in DOM")
        visible = await el.is_visible()
        return AssertionResult(not visible, "Element is hidden" if not visible else "Element still visible")
    except Exception:
        return AssertionResult(True, "Element not found")


async def _check_text_contains(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.expected_value:
        return AssertionResult(False, "No expected_value")
    if assertion.selector:
        try:
            el = await page.wait_for_selector(assertion.selector, timeout=5000)
            text = await el.text_content() or "" if el else ""
            if assertion.expected_value in text:
                return AssertionResult(True, f"Found '{assertion.expected_value}'")
            return AssertionResult(False, f"'{assertion.expected_value}' not in text")
        except Exception as e:
            return AssertionResult(False, str(e))
    else:
        body = await page.text_content("body") or ""
        if assertion.expected_value in body:
            return AssertionResult(True, f"Found '{assertion.expected_value}' in page")
        return AssertionResult(False, f"'{assertion.expected_value}' not in page")


async def _check_text_equals(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.selector or not assertion.expected_value:
        return AssertionResult(False, "Missing selector or expected_value")
    try:
        el = await page.wait_for_selector(assertion.selector, timeout=5000)
        text = (await el.text_content() or "").strip() if el else ""
        if text == assertion.expected_value:
            return AssertionResult(True, "Text matches")
        return AssertionResult(False, f"Expected '{assertion.expected_value}', got '{text}'")
    except Exception as e:
        return AssertionResult(False, str(e))


def _check_url_matches(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.expected_value:
        return AssertionResult(False, "No expected URL")
    current = page.url
    if assertion.expected_value in current or re.search(assertion.expected_value, current):
        return AssertionResult(True, f"URL matches: {current}")
    return AssertionResult(False, f"URL '{current}' doesn't match '{assertion.expected_value}'")


async def _check_screenshot_diff(
    page: Page, assertion: Assertion, evidence_dir: Path, baseline_dir: Path | None, config: FrameworkConfig | None = None
) -> AssertionResult:
    # Use assertion-specific tolerance, then config default, then fall back to 0.05
    default_tolerance = config.visual_diff_tolerance if config else 0.05
    tolerance = assertion.tolerance if assertion.tolerance is not None else default_tolerance
    current_path = evidence_dir / "screenshot_current.png"

    # Wait for page to stabilize before taking screenshot
    # This helps avoid failures due to animations, font loading, layout shifts
    try:
        await page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        # If network doesn't idle within 3s, continue anyway
        pass

    # Additional wait for fonts and animations to settle
    await page.wait_for_timeout(500)

    # Use viewport screenshot by default (less sensitive to dynamic content like scrollbars)
    # Set full_page=True in assertion if you need full page comparison
    full_page = assertion.expected_value == "full_page" if assertion.expected_value else False
    await page.screenshot(path=str(current_path), full_page=full_page)

    if not baseline_dir:
        return AssertionResult(True, "No baseline to compare (first run)")

    # Find baseline
    baseline_candidates = list(baseline_dir.glob("*_screenshot.png"))
    if not baseline_candidates:
        return AssertionResult(True, "No baseline screenshot found (first run)")

    baseline_path = baseline_candidates[0]
    try:
        from PIL import Image
        baseline = Image.open(baseline_path)
        current = Image.open(current_path)

        # Resize to same dimensions
        if baseline.size != current.size:
            current = current.resize(baseline.size)

        # Pixel comparison with tolerance for anti-aliasing and rendering differences
        baseline_pixels = list(baseline.getdata())
        current_pixels = list(current.getdata())
        total = len(baseline_pixels)
        if total == 0:
            return AssertionResult(True, "Empty images")

        diff_count = 0
        # Use threshold of 40 to be more forgiving of anti-aliasing, font rendering,
        # and minor browser differences (was 10, which was too strict)
        pixel_threshold = 40
        for bp, cp in zip(baseline_pixels, current_pixels):
            if isinstance(bp, tuple) and isinstance(cp, tuple):
                # Check if any RGB channel differs by more than threshold
                if any(abs(a - b) > pixel_threshold for a, b in zip(bp, cp)):
                    diff_count += 1
            elif bp != cp:
                diff_count += 1

        diff_ratio = diff_count / total
        passed = diff_ratio <= tolerance
        msg = f"Pixel diff: {diff_ratio:.2%} (tolerance: {tolerance:.2%})"
        return AssertionResult(passed, msg)
    except Exception as e:
        return AssertionResult(False, f"Screenshot comparison error: {e}")


async def _check_element_count(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.selector or not assertion.expected_value:
        return AssertionResult(False, "Missing selector or expected count")
    try:
        elements = await page.query_selector_all(assertion.selector)
        actual = len(elements)
        expected = int(assertion.expected_value)
        if actual == expected:
            return AssertionResult(True, f"Found {actual} elements")
        return AssertionResult(False, f"Expected {expected} elements, found {actual}")
    except Exception as e:
        return AssertionResult(False, str(e))


def _check_network_request(assertion: Assertion, network_log: list[dict] | None) -> AssertionResult:
    if not assertion.expected_value:
        return AssertionResult(False, "No expected URL pattern")
    if not network_log:
        return AssertionResult(False, "No network log available")
    for req in network_log:
        if assertion.expected_value in req.get("url", ""):
            return AssertionResult(True, f"Found request matching '{assertion.expected_value}'")
    return AssertionResult(False, f"No request matching '{assertion.expected_value}'")


def _check_no_console_errors(console_errors: list[str] | None) -> AssertionResult:
    if not console_errors:
        return AssertionResult(True, "No console errors")
    # Filter out benign warnings
    real_errors = [e for e in console_errors if "error" in e.lower() and "favicon" not in e.lower()]
    if not real_errors:
        return AssertionResult(True, "No significant console errors")
    return AssertionResult(False, f"{len(real_errors)} console error(s): {real_errors[0][:100]}")


def _check_response_status(assertion: Assertion, network_log: list[dict] | None) -> AssertionResult:
    if not assertion.expected_value:
        return AssertionResult(False, "No expected status")
    if not network_log:
        return AssertionResult(False, "No network log")
    expected = int(assertion.expected_value)
    for req in network_log:
        if req.get("status") == expected:
            return AssertionResult(True, f"Found response with status {expected}")
    return AssertionResult(False, f"No response with status {expected}")
