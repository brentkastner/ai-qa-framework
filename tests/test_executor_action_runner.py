"""Tests for action runner."""

import pytest
from unittest.mock import AsyncMock, Mock, call

from src.executor.action_runner import run_action
from src.models.test_plan import Action


@pytest.mark.asyncio
class TestRunAction:
    """Tests for run_action function.

    Most tests use smart_resolve=False to isolate the action execution
    logic from the selector resolver. Smart resolution is tested separately.
    """

    async def test_navigate_action(self, mock_page):
        """Test navigate action."""
        action = Action(
            action_type="navigate",
            value="https://example.com",
        )

        await run_action(mock_page, action)

        mock_page.goto.assert_called_once()
        call_args = mock_page.goto.call_args
        assert call_args[0][0] == "https://example.com"

    async def test_navigate_action_uses_selector_if_no_value(self, mock_page):
        """Test navigate can use selector field as URL."""
        action = Action(
            action_type="navigate",
            selector="https://example.com/page",
        )

        await run_action(mock_page, action)

        call_args = mock_page.goto.call_args
        assert call_args[0][0] == "https://example.com/page"

    async def test_click_action(self, mock_page):
        """Test click action."""
        action = Action(
            action_type="click",
            selector="button#submit",
        )

        await run_action(mock_page, action, smart_resolve=False)

        mock_page.click.assert_called_once_with("button#submit", timeout=10000)

    async def test_click_action_requires_selector(self, mock_page):
        """Test click action raises error without selector."""
        action = Action(action_type="click")

        with pytest.raises(ValueError, match="selector"):
            await run_action(mock_page, action, smart_resolve=False)

    async def test_fill_action(self, mock_page):
        """Test fill action."""
        action = Action(
            action_type="fill",
            selector="input[name='email']",
            value="test@example.com",
        )

        await run_action(mock_page, action, smart_resolve=False)

        mock_page.fill.assert_called_once_with(
            "input[name='email']",
            "test@example.com",
            timeout=10000
        )

    async def test_fill_action_with_empty_value(self, mock_page):
        """Test fill action with empty value."""
        action = Action(
            action_type="fill",
            selector="input",
            value=None,
        )

        await run_action(mock_page, action, smart_resolve=False)

        mock_page.fill.assert_called_once_with("input", "", timeout=10000)

    async def test_fill_action_requires_selector(self, mock_page):
        """Test fill action raises error without selector."""
        action = Action(action_type="fill", value="text")

        with pytest.raises(ValueError, match="selector"):
            await run_action(mock_page, action, smart_resolve=False)

    async def test_select_action(self, mock_page):
        """Test select dropdown action."""
        action = Action(
            action_type="select",
            selector="select[name='country']",
            value="USA",
        )

        await run_action(mock_page, action, smart_resolve=False)

        mock_page.select_option.assert_called_once_with(
            "select[name='country']",
            "USA",
            timeout=10000
        )

    async def test_select_action_requires_selector(self, mock_page):
        """Test select action raises error without selector."""
        action = Action(action_type="select", value="option")

        with pytest.raises(ValueError, match="selector"):
            await run_action(mock_page, action, smart_resolve=False)

    async def test_hover_action(self, mock_page):
        """Test hover action."""
        action = Action(
            action_type="hover",
            selector=".menu-item",
        )

        await run_action(mock_page, action, smart_resolve=False)

        mock_page.hover.assert_called_once_with(".menu-item", timeout=10000)

    async def test_hover_action_requires_selector(self, mock_page):
        """Test hover action raises error without selector."""
        action = Action(action_type="hover")

        with pytest.raises(ValueError, match="selector"):
            await run_action(mock_page, action, smart_resolve=False)

    async def test_scroll_to_position(self, mock_page):
        """Test scroll to specific position."""
        action = Action(
            action_type="scroll",
            value="500",
        )

        await run_action(mock_page, action)

        mock_page.evaluate.assert_called_once()
        call_args = mock_page.evaluate.call_args[0][0]
        assert "scrollTo" in call_args
        assert "500" in call_args

    async def test_scroll_to_element(self, mock_page):
        """Test scroll to element."""
        action = Action(
            action_type="scroll",
            selector=".footer",
        )

        await run_action(mock_page, action)

        mock_page.evaluate.assert_called_once()
        call_args = mock_page.evaluate.call_args[0][0]
        assert "querySelector" in call_args
        assert ".footer" in call_args

    async def test_scroll_to_bottom(self, mock_page):
        """Test scroll to bottom when no selector or value."""
        action = Action(action_type="scroll")

        await run_action(mock_page, action)

        mock_page.evaluate.assert_called_once()
        call_args = mock_page.evaluate.call_args[0][0]
        assert "scrollHeight" in call_args

    async def test_wait_for_selector(self, mock_page):
        """Test wait for selector."""
        action = Action(
            action_type="wait",
            selector=".content",
        )

        await run_action(mock_page, action, smart_resolve=False)

        mock_page.wait_for_selector.assert_called_once_with(
            ".content",
            timeout=10000
        )

    async def test_wait_for_timeout(self, mock_page):
        """Test wait for specified time."""
        action = Action(
            action_type="wait",
            value="2000",
        )

        await run_action(mock_page, action)

        mock_page.wait_for_timeout.assert_called_once_with(2000)

    async def test_wait_default_timeout(self, mock_page):
        """Test wait with default 1 second timeout."""
        action = Action(action_type="wait")

        await run_action(mock_page, action)

        mock_page.wait_for_timeout.assert_called_once_with(1000)

    async def test_screenshot_action(self, mock_page):
        """Test screenshot action is a no-op."""
        action = Action(action_type="screenshot")

        # Should not raise any errors
        await run_action(mock_page, action)

        # Screenshot is handled by evidence collector, so page methods shouldn't be called
        mock_page.screenshot.assert_not_called()

    async def test_keyboard_action_with_value(self, mock_page):
        """Test keyboard action with specific key."""
        action = Action(
            action_type="keyboard",
            value="Escape",
        )

        await run_action(mock_page, action)

        mock_page.keyboard.press.assert_called_once_with("Escape")

    async def test_keyboard_action_default_enter(self, mock_page):
        """Test keyboard action defaults to Enter key."""
        action = Action(action_type="keyboard")

        await run_action(mock_page, action)

        mock_page.keyboard.press.assert_called_once_with("Enter")

    async def test_unknown_action_type_logs_warning(self, mock_page):
        """Test unknown action type logs warning but doesn't crash."""
        action = Action(action_type="unknown_action")

        # Should not raise an error
        await run_action(mock_page, action)

    async def test_custom_timeout(self, mock_page):
        """Test actions respect custom timeout parameter."""
        action = Action(
            action_type="click",
            selector="button",
        )

        await run_action(mock_page, action, timeout=5000, smart_resolve=False)

        call_args = mock_page.click.call_args
        assert call_args.kwargs["timeout"] == 5000

    async def test_navigate_waits_for_networkidle(self, mock_page):
        """Test navigate action waits for network idle."""
        action = Action(
            action_type="navigate",
            value="https://example.com",
        )

        await run_action(mock_page, action)

        # Should call wait_for_load_state after goto
        mock_page.wait_for_load_state.assert_called()
        call_args = mock_page.wait_for_load_state.call_args
        assert call_args[0][0] == "networkidle"

    async def test_navigate_continues_if_networkidle_fails(self, mock_page):
        """Test navigate continues even if network idle times out."""
        mock_page.wait_for_load_state.side_effect = Exception("Timeout")
        action = Action(
            action_type="navigate",
            value="https://example.com",
        )

        # Should not raise an error despite wait_for_load_state failing
        await run_action(mock_page, action)

        mock_page.goto.assert_called_once()

    async def test_smart_resolve_uses_resolved_selector(self, mock_page):
        """Test that smart_resolve=True resolves the selector before acting."""
        action = Action(
            action_type="click",
            selector="button#submit",
        )

        # wait_for_selector returns a truthy mock (element found)
        mock_page.wait_for_selector.return_value = AsyncMock()

        await run_action(mock_page, action, timeout=10000, smart_resolve=True)

        # Resolver should have called wait_for_selector to find the element
        mock_page.wait_for_selector.assert_called()
        # Then click should use the resolved (original) selector
        mock_page.click.assert_called_once_with("button#submit", timeout=10000)
