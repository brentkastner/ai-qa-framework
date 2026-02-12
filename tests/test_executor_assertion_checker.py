"""Tests for assertion checker."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from src.executor.assertion_checker import (
    AssertionResult,
    check_assertion,
)
from src.models.config import FrameworkConfig
from src.models.test_plan import Assertion


@pytest.mark.asyncio
class TestCheckAssertion:
    """Tests for check_assertion function."""

    async def test_element_visible_success(self, mock_page, temp_evidence_dir):
        """Test element_visible assertion passes when element is visible."""
        mock_element = AsyncMock()
        mock_page.wait_for_selector.return_value = mock_element

        assertion = Assertion(
            assertion_type="element_visible",
            selector=".success-message",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True
        assert "visible" in result.message.lower()

    async def test_element_visible_failure(self, mock_page, temp_evidence_dir):
        """Test element_visible assertion fails when element not found."""
        mock_page.wait_for_selector.side_effect = Exception("Not found")

        assertion = Assertion(
            assertion_type="element_visible",
            selector=".missing-element",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is False
        assert "not found" in result.message.lower() or "visible" in result.message.lower()

    async def test_element_hidden_when_not_in_dom(self, mock_page, temp_evidence_dir):
        """Test element_hidden passes when element not in DOM."""
        mock_page.query_selector.return_value = None

        assertion = Assertion(
            assertion_type="element_hidden",
            selector=".removed-element",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True

    async def test_text_contains_success(self, mock_page, temp_evidence_dir):
        """Test text_contains assertion passes when text is found."""
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Welcome to our site"
        mock_page.wait_for_selector.return_value = mock_element

        assertion = Assertion(
            assertion_type="text_contains",
            selector="h1",
            expected_value="Welcome",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True

    async def test_text_contains_failure(self, mock_page, temp_evidence_dir):
        """Test text_contains assertion fails when text not found."""
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Different text"
        mock_page.query_selector.return_value = mock_element

        assertion = Assertion(
            assertion_type="text_contains",
            selector="h1",
            expected_value="Welcome",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is False

    async def test_text_equals_success(self, mock_page, temp_evidence_dir):
        """Test text_equals assertion passes for exact match."""
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Exact Match"
        mock_page.wait_for_selector.return_value = mock_element

        assertion = Assertion(
            assertion_type="text_equals",
            selector="span",
            expected_value="Exact Match",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True

    async def test_text_equals_failure(self, mock_page, temp_evidence_dir):
        """Test text_equals assertion fails for non-exact match."""
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Close but not exact"
        mock_page.wait_for_selector.return_value = mock_element

        assertion = Assertion(
            assertion_type="text_equals",
            selector="span",
            expected_value="Exact Match",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is False

    async def test_url_matches_success(self, mock_page, temp_evidence_dir):
        """Test url_matches assertion passes when URL contains pattern."""
        mock_page.url = "https://example.com/dashboard/home"

        assertion = Assertion(
            assertion_type="url_matches",
            expected_value="/dashboard",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True

    async def test_url_matches_failure(self, mock_page, temp_evidence_dir):
        """Test url_matches assertion fails when pattern not in URL."""
        mock_page.url = "https://example.com/login"

        assertion = Assertion(
            assertion_type="url_matches",
            expected_value="/dashboard",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is False

    async def test_element_count_success(self, mock_page, temp_evidence_dir):
        """Test element_count assertion passes with correct count."""
        mock_elements = [Mock(), Mock(), Mock()]
        mock_page.query_selector_all.return_value = mock_elements

        assertion = Assertion(
            assertion_type="element_count",
            selector=".item",
            expected_value="3",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True

    async def test_element_count_failure(self, mock_page, temp_evidence_dir):
        """Test element_count assertion fails with wrong count."""
        mock_elements = [Mock(), Mock()]
        mock_page.query_selector_all.return_value = mock_elements

        assertion = Assertion(
            assertion_type="element_count",
            selector=".item",
            expected_value="5",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is False

    async def test_network_request_made_success(self, mock_page, temp_evidence_dir):
        """Test network_request_made assertion passes when request is in log."""
        network_log = [
            {"url": "/api/users", "method": "GET"},
            {"url": "/api/data", "method": "POST"},
        ]

        assertion = Assertion(
            assertion_type="network_request_made",
            expected_value="/api/users",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, network_log=network_log
        )

        assert result.passed is True

    async def test_network_request_made_failure(self, mock_page, temp_evidence_dir):
        """Test network_request_made assertion fails when request not found."""
        network_log = [
            {"url": "/api/data", "method": "POST"},
        ]

        assertion = Assertion(
            assertion_type="network_request_made",
            expected_value="/api/users",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, network_log=network_log
        )

        assert result.passed is False

    async def test_no_console_errors_success(self, mock_page, temp_evidence_dir):
        """Test no_console_errors assertion passes when no errors."""
        console_errors = []

        assertion = Assertion(assertion_type="no_console_errors")

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, console_errors=console_errors
        )

        assert result.passed is True

    async def test_no_console_errors_failure(self, mock_page, temp_evidence_dir):
        """Test no_console_errors assertion fails when errors exist."""
        console_errors = [
            "Error: Failed to load resource",
            "TypeError: undefined is not a function",
        ]

        assertion = Assertion(assertion_type="no_console_errors")

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, console_errors=console_errors
        )

        assert result.passed is False

    async def test_response_status_success(self, mock_page, temp_evidence_dir):
        """Test response_status assertion passes with matching status."""
        network_log = [
            {"url": "/api/data", "status": 200},
            {"url": "/api/users", "status": 200},
        ]

        assertion = Assertion(
            assertion_type="response_status",
            expected_value="200",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, network_log=network_log
        )

        assert result.passed is True

    async def test_unknown_assertion_type(self, mock_page, temp_evidence_dir):
        """Test unknown assertion type returns failure with error message."""
        assertion = Assertion(assertion_type="unknown_assertion")

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is False
        assert "unknown" in result.message.lower()

    async def test_assertion_error_handled(self, mock_page, temp_evidence_dir):
        """Test exceptions during assertion checking are caught and returned as failures."""
        mock_page.wait_for_selector.side_effect = Exception("Unexpected error")

        assertion = Assertion(
            assertion_type="text_contains",
            selector="h1",
            expected_value="Test",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is False
        assert "error" in result.message.lower()

    async def test_config_visual_tolerance_used(
        self, mock_page, temp_evidence_dir, temp_baseline_dir, create_screenshot_helper
    ):
        """Test screenshot_diff uses config visual_diff_tolerance."""
        # Create baseline and current screenshots
        baseline_path = temp_baseline_dir / "baseline.png"
        current_path = temp_evidence_dir / "current.png"
        create_screenshot_helper(baseline_path)
        create_screenshot_helper(current_path)

        # Mock screenshot capture
        async def mock_screenshot(path, **kwargs):
            create_screenshot_helper(Path(path))

        mock_page.screenshot = AsyncMock(side_effect=mock_screenshot)

        config = FrameworkConfig(
            target_url="https://example.com",
            visual_diff_tolerance=0.15,
        )

        assertion = Assertion(
            assertion_type="screenshot_diff",
            expected_value="baseline.png",
        )

        # The assertion should use config tolerance
        result = await check_assertion(
            mock_page,
            assertion,
            temp_evidence_dir,
            baseline_dir=temp_baseline_dir,
            config=config,
        )

        # Should not fail (both screenshots are identical)
        assert result.passed is True


class TestAssertionResult:
    """Tests for AssertionResult class."""

    def test_create_passed_result(self):
        """Test creating a passed assertion result."""
        result = AssertionResult(True, "Test passed")
        assert result.passed is True
        assert result.message == "Test passed"

    def test_create_failed_result(self):
        """Test creating a failed assertion result."""
        result = AssertionResult(False, "Test failed")
        assert result.passed is False
        assert result.message == "Test failed"

    def test_default_message(self):
        """Test assertion result with default empty message."""
        result = AssertionResult(True)
        assert result.passed is True
        assert result.message == ""
