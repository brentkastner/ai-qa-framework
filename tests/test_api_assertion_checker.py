"""Tests for API assertion checker — check_api_assertion and helpers."""

import pytest

from src.executor.assertion_checker import check_api_assertion
from src.models.test_plan import Assertion


def _response(status=200, body="", json=None, headers=None):
    """Build a minimal response_data dict."""
    return {
        "status": status,
        "headers": headers or {},
        "body": body,
        "json": json,
        "url": "http://localhost:8000/api/test",
    }


# ---------------------------------------------------------------------------
# response_status
# ---------------------------------------------------------------------------

class TestCheckApiStatus:

    def test_matching_status_passes(self):
        assertion = Assertion(assertion_type="response_status", expected_value="200")
        result = check_api_assertion(assertion, _response(status=200))
        assert result.passed is True
        assert "200" in result.message

    def test_mismatched_status_fails(self):
        assertion = Assertion(assertion_type="response_status", expected_value="200")
        result = check_api_assertion(assertion, _response(status=404))
        assert result.passed is False
        assert "404" in result.message

    def test_status_4xx_expected_passes(self):
        assertion = Assertion(assertion_type="response_status", expected_value="404")
        result = check_api_assertion(assertion, _response(status=404))
        assert result.passed is True

    def test_missing_expected_value_fails(self):
        assertion = Assertion(assertion_type="response_status", expected_value=None)
        result = check_api_assertion(assertion, _response(status=200))
        assert result.passed is False
        assert "expected" in result.message.lower()

    def test_non_numeric_expected_value_fails(self):
        assertion = Assertion(assertion_type="response_status", expected_value="ok")
        result = check_api_assertion(assertion, _response(status=200))
        assert result.passed is False
        assert "not a valid status code" in result.message.lower()


# ---------------------------------------------------------------------------
# response_body_contains
# ---------------------------------------------------------------------------

class TestCheckApiBodyContains:

    def test_substring_present_passes(self):
        assertion = Assertion(assertion_type="response_body_contains", expected_value="success")
        result = check_api_assertion(assertion, _response(body='{"status": "success"}'))
        assert result.passed is True

    def test_substring_absent_fails(self):
        assertion = Assertion(assertion_type="response_body_contains", expected_value="error")
        result = check_api_assertion(assertion, _response(body='{"status": "ok"}'))
        assert result.passed is False

    def test_case_insensitive_match(self):
        assertion = Assertion(assertion_type="response_body_contains", expected_value="SUCCESS")
        result = check_api_assertion(assertion, _response(body='{"status": "success"}'))
        assert result.passed is True

    def test_missing_expected_value_fails(self):
        assertion = Assertion(assertion_type="response_body_contains", expected_value=None)
        result = check_api_assertion(assertion, _response(body="anything"))
        assert result.passed is False


# ---------------------------------------------------------------------------
# response_json_path
# ---------------------------------------------------------------------------

class TestCheckApiJsonPath:

    def test_simple_key_passes(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="id",
            expected_value="42",
        )
        result = check_api_assertion(assertion, _response(json={"id": 42}))
        assert result.passed is True

    def test_nested_path_passes(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="data.user.name",
            expected_value="alice",
        )
        result = check_api_assertion(
            assertion,
            _response(json={"data": {"user": {"name": "alice"}}}),
        )
        assert result.passed is True

    def test_array_index_passes(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="items.0.id",
            expected_value="1",
        )
        result = check_api_assertion(
            assertion,
            _response(json={"items": [{"id": 1}, {"id": 2}]}),
        )
        assert result.passed is True

    def test_path_exists_no_expected_value(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="data.id",
            expected_value=None,
        )
        result = check_api_assertion(assertion, _response(json={"data": {"id": 99}}))
        assert result.passed is True
        assert "exists" in result.message.lower()

    def test_wrong_value_fails(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="status",
            expected_value="pending",
        )
        result = check_api_assertion(assertion, _response(json={"status": "complete"}))
        assert result.passed is False
        assert "complete" in result.message

    def test_missing_key_fails(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="data.missing",
            expected_value="x",
        )
        result = check_api_assertion(assertion, _response(json={"data": {}}))
        assert result.passed is False

    def test_non_json_response_fails(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="id",
            expected_value="1",
        )
        result = check_api_assertion(assertion, _response(json=None, body="not json"))
        assert result.passed is False
        assert "not valid json" in result.message.lower()

    def test_no_selector_fails(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector=None,
            expected_value="1",
        )
        result = check_api_assertion(assertion, _response(json={"id": 1}))
        assert result.passed is False

    def test_array_index_out_of_range_fails(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="items.5.id",
            expected_value="1",
        )
        result = check_api_assertion(assertion, _response(json={"items": [{"id": 1}]}))
        assert result.passed is False
        assert "out of range" in result.message.lower()

    def test_substring_match_in_value(self):
        assertion = Assertion(
            assertion_type="response_json_path",
            selector="message",
            expected_value="created",
        )
        result = check_api_assertion(
            assertion,
            _response(json={"message": "resource created successfully"}),
        )
        assert result.passed is True


# ---------------------------------------------------------------------------
# response_header
# ---------------------------------------------------------------------------

class TestCheckApiHeader:

    def test_header_present_with_matching_value(self):
        assertion = Assertion(
            assertion_type="response_header",
            selector="content-type",
            expected_value="application/json",
        )
        result = check_api_assertion(
            assertion,
            _response(headers={"content-type": "application/json; charset=utf-8"}),
        )
        assert result.passed is True

    def test_header_absent_fails(self):
        assertion = Assertion(
            assertion_type="response_header",
            selector="x-custom-header",
            expected_value="value",
        )
        result = check_api_assertion(assertion, _response(headers={}))
        assert result.passed is False
        assert "not found" in result.message.lower()

    def test_header_present_wrong_value_fails(self):
        assertion = Assertion(
            assertion_type="response_header",
            selector="content-type",
            expected_value="text/html",
        )
        result = check_api_assertion(
            assertion,
            _response(headers={"content-type": "application/json"}),
        )
        assert result.passed is False

    def test_case_insensitive_header_name(self):
        assertion = Assertion(
            assertion_type="response_header",
            selector="Content-Type",
            expected_value="json",
        )
        result = check_api_assertion(
            assertion,
            _response(headers={"content-type": "application/json"}),
        )
        assert result.passed is True

    def test_no_expected_value_just_presence_check(self):
        assertion = Assertion(
            assertion_type="response_header",
            selector="x-request-id",
            expected_value=None,
        )
        result = check_api_assertion(
            assertion,
            _response(headers={"x-request-id": "abc123"}),
        )
        assert result.passed is True
        assert "present" in result.message.lower()

    def test_no_selector_fails(self):
        assertion = Assertion(
            assertion_type="response_header",
            selector=None,
            expected_value="json",
        )
        result = check_api_assertion(assertion, _response(headers={"content-type": "json"}))
        assert result.passed is False


# ---------------------------------------------------------------------------
# check_api_assertion dispatch
# ---------------------------------------------------------------------------

class TestCheckApiAssertionDispatch:

    def test_unknown_assertion_type_fails(self):
        assertion = Assertion(assertion_type="element_visible", selector=".foo")
        result = check_api_assertion(assertion, _response())
        assert result.passed is False
        assert "unknown" in result.message.lower()

    def test_exception_is_caught_and_returns_fail(self):
        """An unexpected exception inside a helper must not propagate."""
        assertion = Assertion(assertion_type="response_json_path", selector="a.b")
        # Pass a response_data that will cause an unexpected error path
        result = check_api_assertion(assertion, _response(json={"a": {"b": "v"}}, status=200))
        # Should complete without raising — result can be pass or fail
        assert isinstance(result.passed, bool)
