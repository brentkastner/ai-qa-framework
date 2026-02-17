"""Assertion checker — evaluates test assertions against page state."""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

from playwright.async_api import Page

from src.ai.client import AIClient
from src.ai.prompts.evaluation import EVALUATION_SYSTEM_PROMPT, build_evaluation_prompt
from src.coverage.visual_baseline_registry import VisualBaselineRegistryManager
from src.models.config import FrameworkConfig
from src.models.test_plan import Assertion
from src.models.visual_baseline import VisualBaselineRegistry
from src.url_utils import page_id_from_url

logger = logging.getLogger(__name__)


class AssertionResult:
    def __init__(self, passed: bool, message: str = "", screenshots: list[str] | None = None):
        self.passed = passed
        self.screenshots = screenshots or []
        self.message = message


async def check_assertion(
    page: Page,
    assertion: Assertion,
    evidence_dir: Path,
    baseline_dir: Path | None = None,
    console_errors: list[str] | None = None,
    network_log: list[dict] | None = None,
    config: FrameworkConfig | None = None,
    ai_client: AIClient | None = None,
    visual_registry: VisualBaselineRegistry | None = None,
    visual_registry_manager: VisualBaselineRegistryManager | None = None,
    page_id: str = "",
    run_id: str = "",
) -> AssertionResult:
    """Evaluate a single assertion and return the result."""
    logger.debug("Checking assertion: %s | selector=%s | %s",
                 assertion.assertion_type, assertion.selector,
                 assertion.description or "")
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
            case "text_matches":
                return await _check_text_matches(page, assertion)
            case "url_matches":
                return _check_url_matches(page, assertion)
            case "screenshot_diff":
                return await _check_screenshot_diff(
                    page, assertion, evidence_dir, config,
                    visual_registry, visual_registry_manager,
                    page_id, run_id,
                )
            case "element_count":
                return await _check_element_count(page, assertion)
            case "network_request_made":
                return _check_network_request(assertion, network_log)
            case "no_console_errors":
                return _check_no_console_errors(console_errors)
            case "response_status":
                return _check_response_status(assertion, network_log)
            case "ai_evaluate":
                return await _check_ai_evaluate(page, assertion, evidence_dir, ai_client)
            case "page_title_contains":
                return await _check_page_title_contains(page, assertion)
            case "page_loaded":
                return await _check_page_loaded(page, assertion)
            case _:
                return AssertionResult(False, f"Unknown assertion type: {assertion.assertion_type}")
    except Exception as e:
        logger.debug("Assertion error: %s — %s", assertion.assertion_type, e)
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
        # Use page.title() for <title> selector — more reliable than DOM query
        if assertion.selector.strip().lower() == "title":
            title = await page.title() or ""
            if assertion.expected_value.lower() in title.lower():
                return AssertionResult(True, f"Found '{assertion.expected_value}' in page title '{title}'")
            return AssertionResult(False, f"'{assertion.expected_value}' not in page title '{title}'")
        try:
            el = await page.wait_for_selector(assertion.selector, timeout=5000)
            text = await el.text_content() or "" if el else ""
            if assertion.expected_value.lower() in text.lower():
                return AssertionResult(True, f"Found '{assertion.expected_value}'")
            return AssertionResult(False, f"'{assertion.expected_value}' not in text")
        except Exception as e:
            return AssertionResult(False, str(e))
    else:
        body = await page.text_content("body") or ""
        if assertion.expected_value.lower() in body.lower():
            return AssertionResult(True, f"Found '{assertion.expected_value}' in page")
        return AssertionResult(False, f"'{assertion.expected_value}' not in page")


async def _check_text_equals(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.selector or not assertion.expected_value:
        return AssertionResult(False, "Missing selector or expected_value")
    try:
        # Use page.title() for <title> selector — more reliable than DOM query
        if assertion.selector.strip().lower() == "title":
            text = (await page.title() or "").strip()
        else:
            el = await page.wait_for_selector(assertion.selector, timeout=5000)
            text = (await el.text_content() or "").strip() if el else ""
        if text == assertion.expected_value:
            return AssertionResult(True, "Text matches")
        return AssertionResult(False, f"Expected '{assertion.expected_value}', got '{text}'")
    except Exception as e:
        return AssertionResult(False, str(e))


async def _check_text_matches(page: Page, assertion: Assertion) -> AssertionResult:
    """Regex pattern match against element or page text."""
    if not assertion.expected_value:
        return AssertionResult(False, "No expected_value (regex pattern)")
    try:
        if assertion.selector:
            el = await page.wait_for_selector(assertion.selector, timeout=5000)
            text = await el.text_content() or "" if el else ""
        else:
            text = await page.text_content("body") or ""

        if re.search(assertion.expected_value, text, re.IGNORECASE):
            return AssertionResult(True, f"Pattern '{assertion.expected_value}' matched in text")
        return AssertionResult(False, f"Pattern '{assertion.expected_value}' not found in text")
    except re.error as e:
        return AssertionResult(False, f"Invalid regex pattern: {e}")
    except Exception as e:
        return AssertionResult(False, str(e))


async def _check_page_title_contains(page: Page, assertion: Assertion) -> AssertionResult:
    """Check that the document title contains the expected substring (case-insensitive).

    Uses Playwright's page.title() instead of querying a DOM selector,
    making this resilient to dynamic title suffixes, separators, and CMS changes.
    """
    if not assertion.expected_value:
        return AssertionResult(False, "No expected_value for page_title_contains")
    title = await page.title() or ""
    if assertion.expected_value.lower() in title.lower():
        return AssertionResult(True, f"Page title contains '{assertion.expected_value}' (title: '{title}')")
    return AssertionResult(False, f"Page title '{title}' does not contain '{assertion.expected_value}'")


async def _check_page_loaded(page: Page, assertion: Assertion) -> AssertionResult:
    """Verify that a page loaded successfully without depending on specific text content.

    Checks that the page is not blank (has a title or body content).
    If a selector is provided, also verifies that element is visible.
    """
    title = await page.title() or ""
    body_text = (await page.text_content("body") or "").strip()

    if not title and not body_text:
        return AssertionResult(False, "Page appears blank (no title, no body text)")

    if assertion.selector:
        try:
            el = await page.wait_for_selector(assertion.selector, state="visible", timeout=5000)
            if el:
                return AssertionResult(True, f"Page loaded, key element '{assertion.selector}' visible (title: '{title[:60]}')")
        except Exception:
            return AssertionResult(False, f"Page loaded but key element '{assertion.selector}' not found")

    return AssertionResult(True, f"Page loaded (title: '{title[:60]}')")


def _check_url_matches(page: Page, assertion: Assertion) -> AssertionResult:
    if not assertion.expected_value:
        return AssertionResult(False, "No expected URL")
    current = page.url
    if assertion.expected_value in current or re.search(assertion.expected_value, current):
        return AssertionResult(True, f"URL matches: {current}")
    return AssertionResult(False, f"URL '{current}' doesn't match '{assertion.expected_value}'")


async def _check_screenshot_diff(
    page: Page,
    assertion: Assertion,
    evidence_dir: Path,
    config: FrameworkConfig | None = None,
    visual_registry: VisualBaselineRegistry | None = None,
    visual_registry_manager: VisualBaselineRegistryManager | None = None,
    page_id: str = "",
    run_id: str = "",
) -> AssertionResult:
    """Compare screenshots across all configured viewports in a single assertion."""
    default_tolerance = config.visual_diff_tolerance if config else 0.05
    tolerance = assertion.tolerance if assertion.tolerance is not None else default_tolerance
    full_page = assertion.expected_value == "full_page" if assertion.expected_value else False

    if not visual_registry or not visual_registry_manager:
        return AssertionResult(True, "No visual baseline registry configured (first run)")

    # Resolve the actual page_id from the browser's current URL.
    # The test plan's target_page_id may point to the starting page (e.g. login)
    # but after steps execute, the browser may be on a different page (e.g. dashboard).
    # Only override for valid HTTP URLs — skip about:blank, data:, etc.
    current_url = page.url
    if current_url.startswith(("http://", "https://")):
        actual_page_id = page_id_from_url(current_url)
        if actual_page_id != page_id and page_id:
            logger.info(
                "screenshot_diff: browser is on %s (page_id=%s), "
                "test target was page_id=%s — using actual page for baseline",
                current_url, actual_page_id, page_id,
            )
        page_id = actual_page_id

    if not page_id:
        return AssertionResult(True, "No page_id provided — skipping baseline comparison")

    viewports = config.viewports if config else []
    if not viewports:
        viewports = [type("V", (), {"name": "desktop", "width": 1280, "height": 720})()]

    original_viewport = page.viewport_size
    all_passed = True
    messages: list[str] = []
    captured_screenshots: list[str] = []

    for vp_idx, vp in enumerate(viewports):
        # Resize to this viewport
        logger.debug("Visual diff: viewport %d/%d — %s (%dx%d)",
                     vp_idx + 1, len(viewports), vp.name, vp.width, vp.height)
        await page.set_viewport_size({"width": vp.width, "height": vp.height})

        # Wait for layout to stabilize after resize
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        await page.wait_for_timeout(500)

        # Capture screenshot for this viewport
        current_path = evidence_dir / f"screenshot_{vp.name}.png"
        await page.screenshot(path=str(current_path), full_page=full_page)
        captured_screenshots.append(str(current_path))

        # Look up existing baseline
        entry = visual_registry_manager.get_baseline(visual_registry, page_id, vp.name)

        if entry is None:
            # First run: store as baseline
            visual_registry_manager.store_baseline(
                registry=visual_registry,
                page_id=page_id,
                viewport_name=vp.name,
                viewport_width=vp.width,
                viewport_height=vp.height,
                source_image_path=current_path,
                run_id=run_id,
            )
            messages.append(f"{vp.name} ({vp.width}x{vp.height}): baseline captured")
            continue

        # Compare against stored baseline
        vp_passed, vp_msg = _compare_images(
            visual_registry_manager.get_baseline_image_path(entry),
            current_path, tolerance, page_id, vp.name,
        )
        if not vp_passed:
            all_passed = False
        messages.append(vp_msg)

    # Restore original viewport
    if original_viewport:
        await page.set_viewport_size(original_viewport)

    return AssertionResult(all_passed, "; ".join(messages), screenshots=captured_screenshots)


def _compare_images(
    baseline_path: Path, current_path: Path,
    tolerance: float, page_id: str, viewport_name: str,
) -> tuple[bool, str]:
    """Pixel-compare two images and return (passed, message)."""
    try:
        from PIL import Image

        baseline_img = Image.open(baseline_path)
        current_img = Image.open(current_path)

        if baseline_img.size != current_img.size:
            current_img = current_img.resize(baseline_img.size)

        baseline_pixels = list(baseline_img.getdata())
        current_pixels = list(current_img.getdata())
        total = len(baseline_pixels)
        if total == 0:
            return True, f"{viewport_name}: empty images"

        diff_count = 0
        pixel_threshold = 40
        for bp, cp in zip(baseline_pixels, current_pixels):
            if isinstance(bp, tuple) and isinstance(cp, tuple):
                if any(abs(a - b) > pixel_threshold for a, b in zip(bp, cp)):
                    diff_count += 1
            elif bp != cp:
                diff_count += 1

        diff_ratio = diff_count / total
        passed = diff_ratio <= tolerance
        return passed, f"{viewport_name}: {diff_ratio:.2%} diff (tolerance: {tolerance:.2%})"
    except Exception as e:
        return False, f"{viewport_name}: comparison error: {e}"


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


async def _check_ai_evaluate(
    page: Page, assertion: Assertion, evidence_dir: Path, ai_client: AIClient | None
) -> AssertionResult:
    """Use AI to judge whether a natural language intent is satisfied by the current page state."""
    if not assertion.expected_value:
        return AssertionResult(False, "No intent specified for ai_evaluate (set expected_value)")

    if not ai_client:
        return AssertionResult(False, "ai_evaluate requires an AI client but none is available")

    intent = assertion.expected_value

    try:
        # Capture page state
        screenshot_path = evidence_dir / "ai_evaluate_screenshot.png"
        await page.screenshot(path=str(screenshot_path))

        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        current_url = page.url

        # Get page text, scoped to selector if provided
        if assertion.selector:
            try:
                el = await page.wait_for_selector(assertion.selector, timeout=3000)
                page_text = await el.text_content() or "" if el else ""
            except Exception:
                page_text = await page.text_content("body") or ""
        else:
            page_text = await page.text_content("body") or ""

        user_message = build_evaluation_prompt(intent, current_url, page_text)

        response_text = ai_client.complete_with_image(
            system_prompt=EVALUATION_SYSTEM_PROMPT,
            user_message=user_message,
            image_base64=img_b64,
            max_tokens=500,
        )

        data = AIClient._parse_json_response(response_text)

        passed = data.get("passed", False)
        confidence = data.get("confidence", 0.0)
        reasoning = data.get("reasoning", "No reasoning provided")

        # Treat low-confidence passes as failures
        if passed and confidence < 0.7:
            return AssertionResult(
                False,
                f"AI passed with low confidence ({confidence:.0%}): {reasoning}",
            )

        return AssertionResult(
            passed,
            f"AI verdict ({confidence:.0%} confidence): {reasoning}",
        )

    except Exception as e:
        logger.warning("ai_evaluate failed for intent '%s': %s", intent, e)
        return AssertionResult(False, f"AI evaluation error: {e}")
