"""Tests for smart selector resolution."""

import pytest
from unittest.mock import AsyncMock

from src.executor.selector_resolver import (
    resolve_selector,
    _derive_alternatives,
    _relax_css_selector,
    SelectorResolutionResult,
)


class TestDeriveAlternatives:
    """Tests for _derive_alternatives helper."""

    def test_extracts_id(self):
        alts = _derive_alternatives("div#main-content > button#submit", "click")
        strategy_names = [a[0] for a in alts]
        # Should extract #submit (or #main-content) as a broadened ID selector
        assert "id_only" in strategy_names

    def test_extracts_name_attribute(self):
        alts = _derive_alternatives("input.field[name='email']", "fill")
        strategy_names = [a[0] for a in alts]
        assert "name_attr" in strategy_names
        selectors = [a[1] for a in alts]
        assert '[name="email"]' in selectors

    def test_extracts_placeholder(self):
        alts = _derive_alternatives("input[placeholder='Enter your email']", "fill")
        selectors = [a[1] for a in alts]
        assert any("Enter your email" in s for s in selectors)

    def test_extracts_aria_label(self):
        alts = _derive_alternatives("button[aria-label='Close dialog']", "click")
        selectors = [a[1] for a in alts]
        assert any("Close dialog" in s for s in selectors)

    def test_extracts_text_selector(self):
        alts = _derive_alternatives("text='Submit Order'", "click")
        strategy_names = [a[0] for a in alts]
        assert "text_selector" in strategy_names

    def test_extracts_has_text_for_click(self):
        alts = _derive_alternatives("button:has-text('Add to Cart')", "click")
        strategy_names = [a[0] for a in alts]
        assert "has_text" in strategy_names
        selectors = [a[1] for a in alts]
        assert "text=Add to Cart" in selectors

    def test_no_has_text_for_fill(self):
        """has-text alternatives are only for click/hover actions."""
        alts = _derive_alternatives("div:has-text('Label')", "fill")
        strategy_names = [a[0] for a in alts]
        assert "has_text" not in strategy_names

    def test_generates_relaxed_css(self):
        alts = _derive_alternatives("div.container > ul.list > li:nth-child(3) > a.link", "click")
        strategy_names = [a[0] for a in alts]
        assert "relaxed_css" in strategy_names

    def test_no_duplicates(self):
        """Alternatives should not include the original selector."""
        original = "#submit"
        alts = _derive_alternatives(original, "click")
        selectors = [a[1] for a in alts]
        assert original not in selectors

    def test_empty_for_simple_selector(self):
        """A simple selector with no extractable signals produces few alternatives."""
        alts = _derive_alternatives(".btn", "click")
        # No ID, name, placeholder, aria-label, or text to extract
        # No deep nesting to relax
        assert len(alts) == 0


class TestRelaxCssSelector:
    """Tests for _relax_css_selector."""

    def test_removes_nth_child(self):
        result = _relax_css_selector("ul > li:nth-child(3) > a")
        assert result is not None
        assert ":nth-child" not in result

    def test_removes_first_last_child(self):
        result = _relax_css_selector("div > p:first-child")
        assert result is not None
        assert ":first-child" not in result

    def test_removes_not_pseudo(self):
        result = _relax_css_selector("div:not(.hidden) > span")
        assert result is not None
        assert ":not" not in result

    def test_simplifies_deep_nesting(self):
        result = _relax_css_selector("div.a div.b div.c div.d button.e")
        assert result is not None
        parts = result.split()
        assert len(parts) <= 2

    def test_returns_none_for_playwright_text_selector(self):
        result = _relax_css_selector("text=Submit")
        assert result is None

    def test_returns_none_for_role_selector(self):
        result = _relax_css_selector("role=button")
        assert result is None

    def test_returns_none_when_no_change(self):
        """If nothing can be relaxed, return None."""
        result = _relax_css_selector("button.primary")
        assert result is None

    def test_removes_has_text(self):
        result = _relax_css_selector("button:has-text('Submit')")
        assert result is not None
        assert ":has-text" not in result


@pytest.mark.asyncio
class TestResolveSelector:
    """Tests for resolve_selector function."""

    async def test_original_selector_succeeds(self):
        """When the original selector is found, return it immediately."""
        page = AsyncMock()
        mock_el = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=mock_el)

        result = await resolve_selector(page, "button#submit", timeout_ms=5000)

        assert result.resolved_selector == "button#submit"
        assert result.strategy_used == "original"
        assert len(result.attempts) == 1
        assert result.attempts[0]["success"] is True

    async def test_fallback_to_id_alternative(self):
        """When original fails but broadened ID selector works."""
        page = AsyncMock()

        async def mock_wait(selector, timeout=5000, state="attached"):
            if selector == "div.wrapper > button#submit":
                raise Exception("not found")
            if selector == "#submit":
                return AsyncMock()
            raise Exception("not found")

        page.wait_for_selector = mock_wait
        page.wait_for_load_state = AsyncMock()

        result = await resolve_selector(
            page, "div.wrapper > button#submit", timeout_ms=5000, action_type="click"
        )

        assert result.resolved_selector == "#submit"
        assert result.strategy_used == "id_only"

    async def test_fallback_to_name_alternative(self):
        """When original fails but name attribute selector works."""
        page = AsyncMock()

        async def mock_wait(selector, timeout=5000, state="attached"):
            if selector == 'form.login input[name="email"]':
                raise Exception("not found")
            if selector == '[name="email"]':
                return AsyncMock()
            raise Exception("not found")

        page.wait_for_selector = mock_wait
        page.wait_for_load_state = AsyncMock()

        result = await resolve_selector(
            page, 'form.login input[name="email"]', timeout_ms=5000, action_type="fill"
        )

        assert result.resolved_selector == '[name="email"]'
        assert result.strategy_used == "name_attr"

    async def test_dom_stability_retry_succeeds(self):
        """When original fails initially but succeeds after DOM stability wait."""
        page = AsyncMock()
        call_count = 0

        async def mock_wait(selector, timeout=5000, state="attached"):
            nonlocal call_count
            call_count += 1
            # Fail on first call (original), succeed on second (stability retry)
            if call_count <= 1:
                raise Exception("not found")
            return AsyncMock()

        page.wait_for_selector = mock_wait
        page.wait_for_load_state = AsyncMock()

        # Use a simple selector that generates no alternatives
        result = await resolve_selector(page, ".dynamic-content", timeout_ms=6000)

        assert result.resolved_selector == ".dynamic-content"
        assert result.strategy_used == "dom_stability_retry"

    async def test_all_strategies_fail(self):
        """When all strategies fail, return None."""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("not found"))
        page.wait_for_load_state = AsyncMock()

        result = await resolve_selector(page, "button.nonexistent", timeout_ms=3000)

        assert result.resolved_selector is None
        assert result.strategy_used == "none"
        assert len(result.attempts) >= 2  # At least original + DOM stability retry

    async def test_timeout_passed_to_first_attempt(self):
        """The configured timeout is used for the original selector attempt."""
        page = AsyncMock()
        mock_el = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=mock_el)

        await resolve_selector(page, ".target", timeout_ms=15000)

        page.wait_for_selector.assert_called_once_with(
            ".target", timeout=15000, state="attached"
        )
