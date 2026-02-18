"""Tests for the AI fallback handler."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.ai.client import AIClient
from src.executor.fallback import FallbackHandler, FallbackResponse
from src.models.test_plan import Action
from src.models.test_result import FallbackRecord


class TestFallbackResponse:
    """Tests for FallbackResponse data class."""

    def test_basic_creation(self):
        r = FallbackResponse(decision="skip", reasoning="Could not find element")
        assert r.decision == "skip"
        assert r.reasoning == "Could not find element"
        assert r.new_selector is None
        assert r.new_action is None

    def test_with_new_selector(self):
        r = FallbackResponse(decision="retry", new_selector="button.alt", reasoning="Found alt")
        assert r.new_selector == "button.alt"

    def test_with_new_action(self):
        action = Action(action_type="click", selector="div.fallback")
        r = FallbackResponse(decision="adapt", new_action=action, reasoning="Different target")
        assert r.new_action.selector == "div.fallback"


class TestFallbackHandler:
    """Tests for FallbackHandler."""

    def test_budget_starts_at_max(self):
        handler = FallbackHandler(ai_client=Mock(), max_calls_per_test=3)
        assert handler.budget_remaining == 3

    def test_budget_decrements_on_call(self):
        mock_ai = Mock()
        mock_ai.complete_json.return_value = {"decision": "skip", "reasoning": "nope"}

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector="button#gone")

        handler.request_fallback(
            test_context="Test: Login",
            screenshot_path="",
            dom_snippet="<html></html>",
            console_errors=[],
            original_action=action,
        )

        assert handler.budget_remaining == 2

    def test_budget_exhausted_returns_abort(self):
        handler = FallbackHandler(ai_client=Mock(), max_calls_per_test=0)
        action = Action(action_type="click", selector="button#gone")

        result = handler.request_fallback(
            test_context="Test",
            screenshot_path="",
            dom_snippet="",
            console_errors=[],
            original_action=action,
        )

        assert result.decision == "abort"
        assert "budget" in result.reasoning.lower()

    def test_reset_restores_budget(self):
        mock_ai = Mock()
        mock_ai.complete_json.return_value = {"decision": "skip", "reasoning": ""}

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=2)
        action = Action(action_type="click", selector="button")

        handler.request_fallback("ctx", "", "", [], action)
        handler.request_fallback("ctx", "", "", [], action)
        assert handler.budget_remaining == 0

        handler.reset()
        assert handler.budget_remaining == 2

    def test_retry_decision_with_selector(self):
        mock_ai = Mock()
        mock_ai.complete_json.return_value = {
            "decision": "retry",
            "new_selector": "button.alternative",
            "reasoning": "Found a better selector",
        }

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector="button.original")

        result = handler.request_fallback("ctx", "", "", [], action)

        assert result.decision == "retry"
        assert result.new_selector == "button.alternative"
        assert result.reasoning == "Found a better selector"

    def test_adapt_decision_with_new_action(self):
        mock_ai = Mock()
        mock_ai.complete_json.return_value = {
            "decision": "adapt",
            "new_action": {
                "action_type": "click",
                "selector": "a.login-link",
                "description": "Click login link instead",
            },
            "reasoning": "Button was replaced by a link",
        }

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector="button.login")

        result = handler.request_fallback("ctx", "", "", [], action)

        assert result.decision == "adapt"
        assert result.new_action is not None
        assert result.new_action.action_type == "click"
        assert result.new_action.selector == "a.login-link"

    def test_skip_decision(self):
        mock_ai = Mock()
        mock_ai.complete_json.return_value = {
            "decision": "skip",
            "reasoning": "Element is decorative, skip",
        }

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector=".decoration")

        result = handler.request_fallback("ctx", "", "", [], action)

        assert result.decision == "skip"

    def test_abort_decision(self):
        mock_ai = Mock()
        mock_ai.complete_json.return_value = {
            "decision": "abort",
            "reasoning": "Page is completely different from expected",
        }

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="navigate", value="https://example.com")

        result = handler.request_fallback("ctx", "", "", [], action)

        assert result.decision == "abort"

    def test_uses_image_when_screenshot_exists(self, tmp_path):
        # Create a fake screenshot
        screenshot = tmp_path / "fail.png"
        screenshot.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 50)

        mock_ai = Mock()
        mock_ai.complete_with_image.return_value = '{"decision": "skip", "reasoning": "analyzed"}'

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector="button")

        with patch.object(AIClient, '_parse_json_response', return_value={"decision": "skip", "reasoning": "analyzed"}):
            result = handler.request_fallback("ctx", str(screenshot), "", [], action)

        mock_ai.complete_with_image.assert_called_once()
        assert result.decision == "skip"

    def test_falls_back_to_text_when_no_screenshot(self):
        mock_ai = Mock()
        mock_ai.complete_json.return_value = {"decision": "skip", "reasoning": "no image"}

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector="button")

        result = handler.request_fallback("ctx", "", "", [], action)

        mock_ai.complete_json.assert_called_once()

    def test_handles_json_parse_error(self):
        mock_ai = Mock()
        mock_ai.complete_json.side_effect = ValueError("Invalid JSON")

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector="button")

        result = handler.request_fallback("ctx", "", "", [], action)

        assert result.decision == "skip"
        assert "parse failed" in result.reasoning.lower()

    def test_handles_api_error(self):
        mock_ai = Mock()
        mock_ai.complete_json.side_effect = RuntimeError("Connection refused")
        mock_ai.call_count = 1

        handler = FallbackHandler(ai_client=mock_ai, max_calls_per_test=3)
        action = Action(action_type="click", selector="button")

        with patch.object(AIClient, '_save_parse_failure'):
            result = handler.request_fallback("ctx", "", "", [], action)

        assert result.decision == "skip"
        assert "failed" in result.reasoning.lower()


class TestToRecord:
    """Tests for FallbackHandler.to_record()."""

    def test_converts_to_fallback_record(self):
        handler = FallbackHandler(ai_client=Mock(), max_calls_per_test=3)
        response = FallbackResponse(
            decision="retry", new_selector="button.new",
            reasoning="Found new selector",
        )

        record = handler.to_record(step_index=2, original_selector="button.old", response=response)

        assert isinstance(record, FallbackRecord)
        assert record.step_index == 2
        assert record.original_selector == "button.old"
        assert record.decision == "retry"
        assert record.new_selector == "button.new"
        assert record.reasoning == "Found new selector"

    def test_record_without_new_selector(self):
        handler = FallbackHandler(ai_client=Mock(), max_calls_per_test=3)
        response = FallbackResponse(decision="skip", reasoning="Not important")

        record = handler.to_record(step_index=0, original_selector="div.x", response=response)

        assert record.new_selector is None
