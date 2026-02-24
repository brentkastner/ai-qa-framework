"""Tests for test result data structures."""

import pytest

from src.models.test_result import (
    AssertionResult,
    Evidence,
    FallbackRecord,
    RunResult,
    StepResult,
    TestResult,
)


class TestEvidence:
    """Tests for Evidence model."""

    def test_empty_evidence(self):
        """Test Evidence with default empty values."""
        evidence = Evidence()
        assert evidence.screenshots == []
        assert evidence.console_logs == []
        assert evidence.network_log == []
        assert evidence.dom_snapshot_path is None
        assert evidence.video_path is None

    def test_evidence_with_screenshots(self):
        """Test Evidence with screenshot paths."""
        evidence = Evidence(
            screenshots=["screenshot1.png", "screenshot2.png"]
        )
        assert len(evidence.screenshots) == 2
        assert "screenshot1.png" in evidence.screenshots

    def test_evidence_with_console_logs(self):
        """Test Evidence with console logs."""
        logs = ["Error: Failed to load resource", "Warning: Deprecated API"]
        evidence = Evidence(console_logs=logs)
        assert len(evidence.console_logs) == 2

    def test_evidence_with_network_log(self):
        """Test Evidence with network log."""
        network = [
            {"url": "/api/users", "method": "GET", "status": 200},
            {"url": "/api/data", "method": "POST", "status": 201},
        ]
        evidence = Evidence(network_log=network)
        assert len(evidence.network_log) == 2
        assert evidence.network_log[0]["status"] == 200

    def test_evidence_with_all_data(self):
        """Test Evidence with all fields populated."""
        evidence = Evidence(
            screenshots=["shot.png"],
            console_logs=["log entry"],
            network_log=[{"url": "/api"}],
            dom_snapshot_path="/path/to/dom.html",
            video_path="/path/to/video.mp4",
        )
        assert len(evidence.screenshots) == 1
        assert evidence.dom_snapshot_path == "/path/to/dom.html"
        assert evidence.video_path == "/path/to/video.mp4"


class TestFallbackRecord:
    """Tests for FallbackRecord model."""

    def test_minimal_fallback(self):
        """Test FallbackRecord with minimal fields."""
        record = FallbackRecord(step_index=2)
        assert record.step_index == 2
        assert record.original_selector == ""
        assert record.decision == ""
        assert record.new_selector is None
        assert record.reasoning == ""

    def test_retry_fallback(self):
        """Test retry fallback decision."""
        record = FallbackRecord(
            step_index=1,
            original_selector="button#old",
            decision="retry",
            new_selector="button#new",
            reasoning="Selector updated after DOM change",
        )
        assert record.decision == "retry"
        assert record.new_selector == "button#new"

    def test_skip_fallback(self):
        """Test skip fallback decision."""
        record = FallbackRecord(
            step_index=3,
            original_selector=".optional-element",
            decision="skip",
            reasoning="Element not critical to test",
        )
        assert record.decision == "skip"
        assert record.new_selector is None

    def test_abort_fallback(self):
        """Test abort fallback decision."""
        record = FallbackRecord(
            step_index=0,
            decision="abort",
            reasoning="Test cannot proceed",
        )
        assert record.decision == "abort"

    def test_adapt_fallback(self):
        """Test adapt fallback decision."""
        record = FallbackRecord(
            step_index=2,
            decision="adapt",
            new_selector=".modal-close",
            reasoning="Need to close modal first",
        )
        assert record.decision == "adapt"


class TestStepResult:
    """Tests for StepResult model."""

    def test_minimal_step_result(self):
        """Test StepResult with minimal fields."""
        result = StepResult(
            step_index=0,
            action_type="click",
        )
        assert result.step_index == 0
        assert result.action_type == "click"
        assert result.selector is None
        assert result.value is None
        assert result.description == ""
        assert result.status == "pass"
        assert result.error_message is None
        assert result.screenshot_path is None

    def test_passed_step(self):
        """Test passed step result."""
        result = StepResult(
            step_index=1,
            action_type="fill",
            selector="input[name='email']",
            value="test@example.com",
            description="Fill email field",
            status="pass",
        )
        assert result.status == "pass"
        assert result.value == "test@example.com"
        assert result.error_message is None

    def test_failed_step(self):
        """Test failed step result."""
        result = StepResult(
            step_index=2,
            action_type="click",
            selector="button#missing",
            status="fail",
            error_message="Element not found",
        )
        assert result.status == "fail"
        assert result.error_message == "Element not found"

    def test_skipped_step(self):
        """Test skipped step result."""
        result = StepResult(
            step_index=3,
            action_type="hover",
            selector=".optional",
            status="skip",
        )
        assert result.status == "skip"

    def test_step_with_screenshot(self):
        """Test step result with screenshot."""
        result = StepResult(
            step_index=4,
            action_type="screenshot",
            status="pass",
            screenshot_path="/evidence/step4.png",
        )
        assert result.screenshot_path == "/evidence/step4.png"


class TestAssertionResult:
    """Tests for AssertionResult model."""

    def test_minimal_assertion_result(self):
        """Test AssertionResult with minimal fields."""
        result = AssertionResult(assertion_type="element_visible")
        assert result.assertion_type == "element_visible"
        assert result.selector is None
        assert result.expected_value is None
        assert result.description == ""
        assert result.passed is False
        assert result.actual_value is None
        assert result.message == ""

    def test_passed_assertion(self):
        """Test passed assertion result."""
        result = AssertionResult(
            assertion_type="element_visible",
            selector=".success-message",
            description="Success message visible",
            passed=True,
            actual_value="visible",
            message="Element is visible as expected",
        )
        assert result.passed is True
        assert result.actual_value == "visible"

    def test_failed_assertion(self):
        """Test failed assertion result."""
        result = AssertionResult(
            assertion_type="text_equals",
            selector="h1",
            expected_value="Welcome",
            passed=False,
            actual_value="Hello",
            message="Expected 'Welcome' but got 'Hello'",
        )
        assert result.passed is False
        assert result.expected_value == "Welcome"
        assert result.actual_value == "Hello"

    def test_url_assertion(self):
        """Test URL assertion result."""
        result = AssertionResult(
            assertion_type="url_matches",
            expected_value="/dashboard",
            passed=True,
            actual_value="/dashboard",
        )
        assert result.assertion_type == "url_matches"
        assert result.passed is True

    def test_console_errors_assertion(self):
        """Test no console errors assertion."""
        result = AssertionResult(
            assertion_type="no_console_errors",
            passed=False,
            actual_value="3 errors",
            message="Found 3 console errors",
        )
        assert result.assertion_type == "no_console_errors"
        assert result.passed is False


class TestTestResult:
    """Tests for TestResult model."""

    def test_minimal_test_result(self):
        """Test TestResult with minimal required fields."""
        result = TestResult(
            test_id="test-001",
            test_name="Basic Test",
            category="functional",
            result="pass",
        )
        assert result.test_id == "test-001"
        assert result.test_name == "Basic Test"
        assert result.category == "functional"
        assert result.result == "pass"
        assert result.duration_seconds == 0.0
        assert result.failure_reason is None
        assert isinstance(result.evidence, Evidence)
        assert result.fallback_records == []

    def test_passed_test(self):
        """Test passed test result."""
        step = StepResult(step_index=0, action_type="click", status="pass")
        assertion = AssertionResult(assertion_type="element_visible", passed=True)

        result = TestResult(
            test_id="test-001",
            test_name="Login Test",
            category="functional",
            priority=1,
            result="pass",
            duration_seconds=2.5,
            step_results=[step],
            assertion_results=[assertion],
            assertions_passed=1,
            assertions_total=1,
        )
        assert result.result == "pass"
        assert result.duration_seconds == 2.5
        assert result.assertions_passed == 1
        assert len(result.step_results) == 1

    def test_failed_test(self):
        """Test failed test result."""
        assertion = AssertionResult(
            assertion_type="text_equals",
            passed=False,
            message="Text mismatch",
        )

        result = TestResult(
            test_id="test-002",
            test_name="Form Validation",
            category="functional",
            result="fail",
            failure_reason="Assertion failed: Text mismatch",
            assertion_results=[assertion],
            assertions_failed=1,
            assertions_total=1,
        )
        assert result.result == "fail"
        assert result.failure_reason is not None
        assert result.assertions_failed == 1

    def test_skipped_test(self):
        """Test skipped test result."""
        result = TestResult(
            test_id="test-003",
            test_name="Optional Test",
            category="visual",
            result="skip",
            failure_reason="Precondition not met",
        )
        assert result.result == "skip"

    def test_error_test(self):
        """Test test result with error."""
        result = TestResult(
            test_id="test-004",
            test_name="Broken Test",
            category="functional",
            result="error",
            failure_reason="Browser crashed",
        )
        assert result.result == "error"

    def test_test_with_evidence(self):
        """Test test result with evidence."""
        evidence = Evidence(
            screenshots=["step1.png", "step2.png"],
            console_logs=["log entry"],
        )
        result = TestResult(
            test_id="test-005",
            test_name="Test with Evidence",
            category="functional",
            result="pass",
            evidence=evidence,
        )
        assert len(result.evidence.screenshots) == 2

    def test_test_with_fallbacks(self):
        """Test test result with fallback records."""
        fallback = FallbackRecord(
            step_index=1,
            decision="retry",
            reasoning="Selector updated",
        )
        result = TestResult(
            test_id="test-006",
            test_name="Test with Fallbacks",
            category="functional",
            result="pass",
            fallback_records=[fallback],
        )
        assert len(result.fallback_records) == 1

    def test_test_with_preconditions(self):
        """Test test result with precondition results."""
        precondition = StepResult(
            step_index=0,
            action_type="navigate",
            status="pass",
        )
        result = TestResult(
            test_id="test-007",
            test_name="Test with Preconditions",
            category="functional",
            result="pass",
            precondition_results=[precondition],
        )
        assert len(result.precondition_results) == 1


    def test_potentially_flaky_default_false(self):
        """Test potentially_flaky defaults to False."""
        result = TestResult(
            test_id="t1", test_name="Test", category="functional", result="pass",
        )
        assert result.potentially_flaky is False

    def test_potentially_flaky_set_true(self):
        """Test potentially_flaky can be set to True."""
        result = TestResult(
            test_id="t1", test_name="Test", category="functional", result="fail",
            potentially_flaky=True,
        )
        assert result.potentially_flaky is True

    def test_potentially_flaky_serialization(self):
        """Test potentially_flaky survives serialization round-trip."""
        result = TestResult(
            test_id="t1", test_name="Test", category="functional", result="fail",
            potentially_flaky=True,
        )
        data = result.model_dump()
        assert data["potentially_flaky"] is True
        restored = TestResult(**data)
        assert restored.potentially_flaky is True


class TestRunResult:
    """Tests for RunResult model."""

    def test_minimal_run_result(self):
        """Test RunResult with minimal fields."""
        result = RunResult(
            run_id="run-001",
            plan_id="plan-001",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
        )
        assert result.run_id == "run-001"
        assert result.plan_id == "plan-001"
        assert result.target_url == "https://example.com"
        assert result.total_tests == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.errors == 0
        assert result.duration_seconds == 0.0
        assert result.test_results == []
        assert result.ai_summary == ""

    def test_run_with_test_results(self):
        """Test RunResult with test results."""
        test1 = TestResult(
            test_id="t1", test_name="Test 1", category="functional", result="pass"
        )
        test2 = TestResult(
            test_id="t2", test_name="Test 2", category="visual", result="fail"
        )

        result = RunResult(
            run_id="run-001",
            plan_id="plan-001",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:10:00Z",
            target_url="https://example.com",
            total_tests=2,
            passed=1,
            failed=1,
            duration_seconds=600.0,
            test_results=[test1, test2],
        )
        assert result.total_tests == 2
        assert result.passed == 1
        assert result.failed == 1
        assert len(result.test_results) == 2
        assert result.duration_seconds == 600.0

    def test_run_with_all_statuses(self):
        """Test RunResult with all test statuses."""
        result = RunResult(
            run_id="run-002",
            plan_id="plan-002",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:15:00Z",
            target_url="https://example.com",
            total_tests=10,
            passed=5,
            failed=2,
            skipped=2,
            errors=1,
        )
        assert result.total_tests == 10
        assert result.passed == 5
        assert result.failed == 2
        assert result.skipped == 2
        assert result.errors == 1
        # Total should equal sum of statuses
        assert result.total_tests == (
            result.passed + result.failed + result.skipped + result.errors
        )

    def test_run_with_ai_summary(self):
        """Test RunResult with AI summary."""
        summary = "All critical tests passed. 2 minor visual regressions detected."
        result = RunResult(
            run_id="run-003",
            plan_id="plan-003",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:20:00Z",
            target_url="https://example.com",
            ai_summary=summary,
        )
        assert result.ai_summary == summary
        assert "visual regressions" in result.ai_summary

    def test_serialization(self):
        """Test RunResult serialization."""
        test = TestResult(
            test_id="t1", test_name="Test", category="functional", result="pass"
        )
        result = RunResult(
            run_id="run-001",
            plan_id="plan-001",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            total_tests=1,
            passed=1,
            test_results=[test],
        )
        data = result.model_dump()
        assert data["run_id"] == "run-001"
        assert data["total_tests"] == 1
        assert len(data["test_results"]) == 1
