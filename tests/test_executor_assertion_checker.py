"""Tests for assertion checker."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from src.ai.client import AIClient
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
        mock_page.wait_for_selector.return_value = mock_element

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


@pytest.mark.asyncio
class TestTextContainsCaseInsensitive:
    """Tests for case-insensitive text_contains behavior."""

    async def test_text_contains_case_insensitive_match(self, mock_page, temp_evidence_dir):
        """Test text_contains matches regardless of case."""
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Welcome to Your Dashboard"
        mock_page.wait_for_selector.return_value = mock_element

        assertion = Assertion(
            assertion_type="text_contains",
            selector="h1",
            expected_value="welcome",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is True

    async def test_text_contains_case_insensitive_page_level(self, mock_page, temp_evidence_dir):
        """Test text_contains is case-insensitive at page level too."""
        mock_page.text_content.return_value = "LOGIN SUCCESSFUL - Welcome Back"

        assertion = Assertion(
            assertion_type="text_contains",
            expected_value="login successful",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is True

    async def test_text_contains_still_fails_when_not_present(self, mock_page, temp_evidence_dir):
        """Test text_contains still fails when text is genuinely absent."""
        mock_page.text_content.return_value = "Page Not Found"

        assertion = Assertion(
            assertion_type="text_contains",
            expected_value="success",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is False


@pytest.mark.asyncio
class TestTextMatches:
    """Tests for text_matches regex assertion type."""

    async def test_text_matches_simple_pattern(self, mock_page, temp_evidence_dir):
        """Test text_matches with a simple regex pattern."""
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Welcome back, John!"
        mock_page.wait_for_selector.return_value = mock_element

        assertion = Assertion(
            assertion_type="text_matches",
            selector="h1",
            expected_value=r"Welcome.*John",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is True

    async def test_text_matches_alternation_pattern(self, mock_page, temp_evidence_dir):
        """Test text_matches with alternation pattern for flexible matching."""
        mock_page.text_content.return_value = "Your Dashboard - Overview"

        assertion = Assertion(
            assertion_type="text_matches",
            expected_value=r"Dashboard|Welcome|My Account",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is True

    async def test_text_matches_case_insensitive(self, mock_page, temp_evidence_dir):
        """Test text_matches is case-insensitive by default."""
        mock_page.text_content.return_value = "DASHBOARD OVERVIEW"

        assertion = Assertion(
            assertion_type="text_matches",
            expected_value=r"dashboard",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is True

    async def test_text_matches_failure(self, mock_page, temp_evidence_dir):
        """Test text_matches fails when pattern doesn't match."""
        mock_page.text_content.return_value = "Login Page"

        assertion = Assertion(
            assertion_type="text_matches",
            expected_value=r"Dashboard|Welcome|Account",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is False

    async def test_text_matches_invalid_regex(self, mock_page, temp_evidence_dir):
        """Test text_matches handles invalid regex gracefully."""
        mock_page.text_content.return_value = "Some text"

        assertion = Assertion(
            assertion_type="text_matches",
            expected_value=r"[invalid(",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is False
        assert "invalid regex" in result.message.lower()

    async def test_text_matches_no_expected_value(self, mock_page, temp_evidence_dir):
        """Test text_matches fails with no pattern."""
        assertion = Assertion(
            assertion_type="text_matches",
        )

        result = await check_assertion(mock_page, assertion, temp_evidence_dir)
        assert result.passed is False


@pytest.mark.asyncio
class TestAiEvaluate:
    """Tests for ai_evaluate assertion type."""

    async def test_ai_evaluate_passes_with_high_confidence(
        self, mock_page, temp_evidence_dir, mock_ai_client
    ):
        """Test ai_evaluate passes when AI returns passed=true with high confidence."""
        # Mock screenshot capture
        async def mock_screenshot(path, **kwargs):
            Path(path).write_bytes(b"fake_png_data")

        mock_page.screenshot = AsyncMock(side_effect=mock_screenshot)
        mock_page.url = "https://example.com/dashboard"
        mock_page.text_content.return_value = "Welcome to your dashboard"

        mock_ai_client.complete_with_image.return_value = (
            '{"passed": true, "confidence": 0.95, "reasoning": "User is on dashboard page"}'
        )

        assertion = Assertion(
            assertion_type="ai_evaluate",
            expected_value="user appears to be logged in",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, ai_client=mock_ai_client
        )

        assert result.passed is True
        assert "95%" in result.message
        assert "dashboard" in result.message.lower()

    async def test_ai_evaluate_fails_when_ai_says_no(
        self, mock_page, temp_evidence_dir, mock_ai_client
    ):
        """Test ai_evaluate fails when AI returns passed=false."""
        async def mock_screenshot(path, **kwargs):
            Path(path).write_bytes(b"fake_png_data")

        mock_page.screenshot = AsyncMock(side_effect=mock_screenshot)
        mock_page.url = "https://example.com/login"
        mock_page.text_content.return_value = "Please enter your credentials"

        mock_ai_client.complete_with_image.return_value = (
            '{"passed": false, "confidence": 0.9, "reasoning": "Still on login page"}'
        )

        assertion = Assertion(
            assertion_type="ai_evaluate",
            expected_value="user appears to be logged in",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, ai_client=mock_ai_client
        )

        assert result.passed is False

    async def test_ai_evaluate_low_confidence_pass_treated_as_failure(
        self, mock_page, temp_evidence_dir, mock_ai_client
    ):
        """Test ai_evaluate treats low-confidence passes as failures."""
        async def mock_screenshot(path, **kwargs):
            Path(path).write_bytes(b"fake_png_data")

        mock_page.screenshot = AsyncMock(side_effect=mock_screenshot)
        mock_page.url = "https://example.com/unknown"
        mock_page.text_content.return_value = "Loading..."

        mock_ai_client.complete_with_image.return_value = (
            '{"passed": true, "confidence": 0.4, "reasoning": "Page is still loading, unclear"}'
        )

        assertion = Assertion(
            assertion_type="ai_evaluate",
            expected_value="page has fully loaded",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, ai_client=mock_ai_client
        )

        assert result.passed is False
        assert "low confidence" in result.message.lower()

    async def test_ai_evaluate_no_ai_client(self, mock_page, temp_evidence_dir):
        """Test ai_evaluate fails gracefully when no AI client is available."""
        assertion = Assertion(
            assertion_type="ai_evaluate",
            expected_value="user is logged in",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, ai_client=None
        )

        assert result.passed is False
        assert "requires an AI client" in result.message

    async def test_ai_evaluate_no_intent(self, mock_page, temp_evidence_dir, mock_ai_client):
        """Test ai_evaluate fails when no intent is provided."""
        assertion = Assertion(
            assertion_type="ai_evaluate",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, ai_client=mock_ai_client
        )

        assert result.passed is False
        assert "no intent" in result.message.lower()

    async def test_ai_evaluate_with_selector(
        self, mock_page, temp_evidence_dir, mock_ai_client
    ):
        """Test ai_evaluate scopes text extraction to selector when provided."""
        async def mock_screenshot(path, **kwargs):
            Path(path).write_bytes(b"fake_png_data")

        mock_page.screenshot = AsyncMock(side_effect=mock_screenshot)
        mock_page.url = "https://example.com/dashboard"

        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Welcome, John"
        mock_page.wait_for_selector.return_value = mock_element

        mock_ai_client.complete_with_image.return_value = (
            '{"passed": true, "confidence": 0.92, "reasoning": "User greeting visible"}'
        )

        assertion = Assertion(
            assertion_type="ai_evaluate",
            selector=".user-greeting",
            expected_value="user greeting is displayed",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, ai_client=mock_ai_client
        )

        assert result.passed is True
        mock_page.wait_for_selector.assert_called_with(".user-greeting", timeout=3000)

    async def test_ai_evaluate_handles_ai_error(
        self, mock_page, temp_evidence_dir, mock_ai_client
    ):
        """Test ai_evaluate handles AI call failures gracefully."""
        async def mock_screenshot(path, **kwargs):
            Path(path).write_bytes(b"fake_png_data")

        mock_page.screenshot = AsyncMock(side_effect=mock_screenshot)
        mock_page.url = "https://example.com"
        mock_page.text_content.return_value = "Page content"

        mock_ai_client.complete_with_image.side_effect = Exception("API error")

        assertion = Assertion(
            assertion_type="ai_evaluate",
            expected_value="page loaded correctly",
        )

        result = await check_assertion(
            mock_page, assertion, temp_evidence_dir, ai_client=mock_ai_client
        )

        assert result.passed is False
        assert "error" in result.message.lower()
