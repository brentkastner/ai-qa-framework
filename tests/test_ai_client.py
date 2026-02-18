"""Tests for AI client."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import anthropic
import pytest

from src.ai.client import AIClient, set_debug_dir, _get_debug_dir


class TestAIClient:
    """Tests for AIClient class."""

    def test_init_requires_api_key(self):
        """Test AIClient raises error when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                AIClient()

    @patch("anthropic.Anthropic")
    def test_init_with_api_key(self, mock_anthropic):
        """Test AIClient initializes with valid API key."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()
            assert client.model == "claude-opus-4-6"
            assert client.max_tokens == 32000
            assert client.call_count == 0
            mock_anthropic.assert_called_once()

    @patch("anthropic.Anthropic")
    def test_init_with_custom_model(self, mock_anthropic):
        """Test AIClient with custom model."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient(model="claude-opus-4-6")
            assert client.model == "claude-opus-4-6"

    @patch("anthropic.Anthropic")
    def test_init_with_custom_max_tokens(self, mock_anthropic):
        """Test AIClient with custom max_tokens."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient(max_tokens=16000)
            assert client.max_tokens == 16000

    @patch("anthropic.Anthropic")
    def test_complete_success(self, mock_anthropic_class):
        """Test successful completion request."""
        # Setup mock response
        mock_content = Mock()
        mock_content.text = "AI response text"
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            # Mock the _save_exchange_log method to avoid file I/O
            with patch.object(client, '_save_exchange_log'):
                response = client.complete(
                    system_prompt="You are a helpful assistant",
                    user_message="Hello",
                )

                assert response == "AI response text"
                assert client.call_count == 1
                mock_client.messages.create.assert_called_once()

    @patch("anthropic.Anthropic")
    def test_complete_increments_call_count(self, mock_anthropic_class):
        """Test complete method increments call counter."""
        mock_content = Mock()
        mock_content.text = "Response"
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                assert client.call_count == 0
                client.complete("system", "user1")
                assert client.call_count == 1
                client.complete("system", "user2")
                assert client.call_count == 2

    @patch("anthropic.Anthropic")
    def test_complete_uses_custom_max_tokens(self, mock_anthropic_class):
        """Test complete method respects custom max_tokens parameter."""
        mock_content = Mock()
        mock_content.text = "Response"
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient(max_tokens=8000)

            with patch.object(client, '_save_exchange_log'):
                client.complete("system", "user", max_tokens=16000)

                call_args = mock_client.messages.create.call_args
                assert call_args.kwargs["max_tokens"] == 16000

    @patch("anthropic.Anthropic")
    def test_complete_uses_temperature(self, mock_anthropic_class):
        """Test complete method uses temperature parameter."""
        mock_content = Mock()
        mock_content.text = "Response"
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                client.complete("system", "user", temperature=0.7)

                call_args = mock_client.messages.create.call_args
                assert call_args.kwargs["temperature"] == 0.7

    @patch("anthropic.Anthropic")
    @patch("src.ai.client.logger")
    def test_complete_warns_on_truncation(self, mock_logger, mock_anthropic_class):
        """Test complete method logs warning when response is truncated."""
        mock_content = Mock()
        mock_content.text = "Truncated response..."
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "max_tokens"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                client.complete("system", "user")

                # Check that warning was logged
                mock_logger.warning.assert_called()
                warning_call = mock_logger.warning.call_args[0][0]
                assert "truncated" in warning_call.lower()

    @patch("anthropic.Anthropic")
    def test_complete_json_parses_valid_response(self, mock_anthropic_class):
        """Test complete_json successfully parses valid JSON."""
        json_response = '{"result": "success", "data": [1, 2, 3]}'
        mock_content = Mock()
        mock_content.text = json_response
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                result = client.complete_json("system", "user")

                assert isinstance(result, dict)
                assert result["result"] == "success"
                assert result["data"] == [1, 2, 3]

    @patch("anthropic.Anthropic")
    def test_complete_json_strips_markdown_fences(self, mock_anthropic_class):
        """Test complete_json strips markdown code fences."""
        json_with_fences = '```json\n{"result": "success"}\n```'
        mock_content = Mock()
        mock_content.text = json_with_fences
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                with patch.object(client, '_save_parse_failure'):
                    result = client.complete_json("system", "user")

                    assert isinstance(result, dict)
                    assert result["result"] == "success"

    @patch("anthropic.Anthropic")
    def test_complete_json_raises_on_invalid_json(self, mock_anthropic_class):
        """Test complete_json raises error on invalid JSON."""
        invalid_json = "This is not JSON"
        mock_content = Mock()
        mock_content.text = invalid_json
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                with patch.object(client, '_save_parse_failure'):
                    with pytest.raises(ValueError, match="invalid JSON"):
                        client.complete_json("system", "user")


class TestDebugDirectory:
    """Tests for debug directory functions."""

    def test_set_debug_dir_creates_directory(self, tmp_path: Path):
        """Test set_debug_dir creates the directory."""
        debug_dir = tmp_path / "debug"
        set_debug_dir(debug_dir)
        assert debug_dir.exists()
        assert debug_dir.is_dir()

    def test_get_debug_dir_returns_path(self):
        """Test _get_debug_dir returns a valid path."""
        debug_dir = _get_debug_dir()
        assert isinstance(debug_dir, Path)
        assert debug_dir.exists()

    def test_get_debug_dir_creates_if_missing(self, tmp_path: Path):
        """Test _get_debug_dir creates directory if it doesn't exist."""
        # Set to a path that doesn't exist yet
        test_dir = tmp_path / "new_debug"
        set_debug_dir(test_dir)

        # Should create it
        result = _get_debug_dir()
        assert result.exists()


class TestAIClientErrorHandling:
    """Tests for AIClient error handling."""

    @patch("anthropic.Anthropic")
    def test_api_error_propagates(self, mock_anthropic_class):
        """Test API errors are propagated to caller."""
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with pytest.raises(Exception, match="API Error"):
                client.complete("system", "user")

    @patch("time.sleep")
    @patch("anthropic.Anthropic")
    def test_timeout_error_propagates_after_retries(self, mock_anthropic_class, mock_sleep):
        """Test timeout errors are propagated after exhausting retries."""
        import anthropic

        mock_client = Mock()
        mock_client.messages.create.side_effect = anthropic.APITimeoutError(
            request=Mock()
        )
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with pytest.raises(anthropic.APITimeoutError):
                client.complete("system", "user")

            # Should have retried MAX_RETRIES times (1 initial + 3 retries = 4 calls)
            assert mock_client.messages.create.call_count == 1 + AIClient.MAX_RETRIES
            assert mock_sleep.call_count == AIClient.MAX_RETRIES


class TestAIClientRetry:
    """Tests for API retry with exponential backoff."""

    def _make_success_response(self):
        mock_content = Mock()
        mock_content.text = "OK"
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"
        return mock_response

    def test_is_retryable_overloaded(self):
        """529 (overloaded) errors are retryable."""
        error = anthropic.APIStatusError(
            message="overloaded", response=Mock(status_code=529), body=None,
        )
        assert AIClient._is_retryable(error) is True

    def test_is_retryable_rate_limit(self):
        """429 (rate limit) errors are retryable."""
        error = anthropic.APIStatusError(
            message="rate limited", response=Mock(status_code=429), body=None,
        )
        assert AIClient._is_retryable(error) is True

    def test_is_retryable_server_errors(self):
        """5xx server errors are retryable."""
        for code in (500, 502, 503, 504):
            error = anthropic.APIStatusError(
                message="server error", response=Mock(status_code=code), body=None,
            )
            assert AIClient._is_retryable(error) is True, f"Expected {code} to be retryable"

    def test_is_retryable_connection_error(self):
        """Connection errors are retryable."""
        error = anthropic.APIConnectionError(request=Mock())
        assert AIClient._is_retryable(error) is True

    def test_is_not_retryable_auth_error(self):
        """401 (auth) errors are NOT retryable."""
        error = anthropic.APIStatusError(
            message="unauthorized", response=Mock(status_code=401), body=None,
        )
        assert AIClient._is_retryable(error) is False

    def test_is_not_retryable_bad_request(self):
        """400 (bad request) errors are NOT retryable."""
        error = anthropic.APIStatusError(
            message="bad request", response=Mock(status_code=400), body=None,
        )
        assert AIClient._is_retryable(error) is False

    @patch("time.sleep")
    @patch("anthropic.Anthropic")
    def test_retry_succeeds_after_transient_failure(self, mock_anthropic_class, mock_sleep):
        """Test successful recovery after a transient 529 error."""
        success = self._make_success_response()
        overloaded = anthropic.APIStatusError(
            message="overloaded", response=Mock(status_code=529), body=None,
        )

        mock_client = Mock()
        mock_client.messages.create.side_effect = [overloaded, success]
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()
            with patch.object(client, '_save_exchange_log'):
                result = client.complete("system", "user")

        assert result == "OK"
        assert mock_client.messages.create.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("time.sleep")
    @patch("anthropic.Anthropic")
    def test_retry_gives_up_after_max_retries(self, mock_anthropic_class, mock_sleep):
        """Test that retries are exhausted and error is raised."""
        overloaded = anthropic.APIStatusError(
            message="overloaded", response=Mock(status_code=529), body=None,
        )

        mock_client = Mock()
        mock_client.messages.create.side_effect = overloaded
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()
            with pytest.raises(anthropic.APIStatusError):
                client.complete("system", "user")

        assert mock_client.messages.create.call_count == 1 + AIClient.MAX_RETRIES
        assert mock_sleep.call_count == AIClient.MAX_RETRIES

    @patch("time.sleep")
    @patch("anthropic.Anthropic")
    def test_non_retryable_error_fails_immediately(self, mock_anthropic_class, mock_sleep):
        """Test that non-retryable errors are raised without retry."""
        auth_error = anthropic.APIStatusError(
            message="unauthorized", response=Mock(status_code=401), body=None,
        )

        mock_client = Mock()
        mock_client.messages.create.side_effect = auth_error
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()
            with pytest.raises(anthropic.APIStatusError):
                client.complete("system", "user")

        assert mock_client.messages.create.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("time.sleep")
    @patch("anthropic.Anthropic")
    def test_backoff_delay_increases_exponentially(self, mock_anthropic_class, mock_sleep):
        """Test that retry delays follow exponential backoff."""
        overloaded = anthropic.APIStatusError(
            message="overloaded", response=Mock(status_code=529), body=None,
        )

        mock_client = Mock()
        mock_client.messages.create.side_effect = overloaded
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()
            with patch("random.uniform", return_value=0.5):
                with pytest.raises(anthropic.APIStatusError):
                    client.complete("system", "user")

        # Delays: 1*2^0+0.5=1.5, 1*2^1+0.5=2.5, 1*2^2+0.5=4.5
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.5, 2.5, 4.5]

    @patch("time.sleep")
    @patch("anthropic.Anthropic")
    def test_retry_works_for_complete_with_image(self, mock_anthropic_class, mock_sleep):
        """Test retry logic also applies to complete_with_image."""
        success = self._make_success_response()
        overloaded = anthropic.APIStatusError(
            message="overloaded", response=Mock(status_code=529), body=None,
        )

        mock_client = Mock()
        mock_client.messages.create.side_effect = [overloaded, success]
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()
            with patch.object(client, '_save_exchange_log'):
                result = client.complete_with_image(
                    "system", "describe this", image_base64="abc123"
                )

        assert result == "OK"
        assert mock_client.messages.create.call_count == 2


@pytest.mark.unit
class TestAIClientIntegration:
    """Integration-style tests for AIClient (still using mocks but testing more complete flows)."""

    @patch("anthropic.Anthropic")
    def test_multiple_calls_track_correctly(self, mock_anthropic_class):
        """Test multiple API calls are tracked correctly."""
        mock_content = Mock()
        mock_content.text = "Response"
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                for i in range(5):
                    client.complete(f"system {i}", f"user {i}")

                assert client.call_count == 5
                assert mock_client.messages.create.call_count == 5

    @patch("anthropic.Anthropic")
    def test_json_and_text_calls_both_work(self, mock_anthropic_class):
        """Test mixing JSON and text calls."""
        text_content = Mock()
        text_content.text = "Plain text response"
        text_response = Mock()
        text_response.content = [text_content]
        text_response.stop_reason = "end_turn"

        json_content = Mock()
        json_content.text = '{"key": "value"}'
        json_response = Mock()
        json_response.content = [json_content]
        json_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.side_effect = [text_response, json_response]
        mock_anthropic_class.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            with patch.object(client, '_save_exchange_log'):
                with patch.object(client, '_save_parse_failure'):
                    text_result = client.complete("system", "user")
                    json_result = client.complete_json("system", "user")

                    assert text_result == "Plain text response"
                    assert json_result == {"key": "value"}
                    assert client.call_count == 2
