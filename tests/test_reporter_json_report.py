"""Tests for JSON report generation."""

import json
from pathlib import Path

import pytest

from src.reporter.json_report import generate_json_report
from src.models.test_result import (
    AssertionResult,
    Evidence,
    RunResult,
    StepResult,
    TestResult,
)


class TestGenerateJsonReport:
    """Tests for generate_json_report function."""

    def test_generate_basic_report(self, tmp_path: Path):
        """Test generating a basic JSON report."""
        run_result = RunResult(
            run_id="run-001",
            plan_id="plan-001",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            total_tests=1,
            passed=1,
            duration_seconds=300.0,
        )

        output_file = tmp_path / "report.json"
        generate_json_report(run_result, [], output_file)

        assert output_file.exists()

        # Verify JSON is valid and contains expected data
        with open(output_file) as f:
            data = json.load(f)

        assert data["run_id"] == "run-001"
        assert data["total_tests"] == 1
        assert data["passed"] == 1

    def test_report_includes_all_run_details(self, tmp_path: Path):
        """Test report includes all run result details."""
        run_result = RunResult(
            run_id="run-002",
            plan_id="plan-002",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:10:00Z",
            target_url="https://example.com",
            total_tests=10,
            passed=7,
            failed=2,
            skipped=1,
            errors=0,
            duration_seconds=600.0,
            ai_summary="Test summary",
        )

        output_file = tmp_path / "report.json"
        generate_json_report(run_result, [], output_file)

        with open(output_file) as f:
            data = json.load(f)

        assert data["total_tests"] == 10
        assert data["passed"] == 7
        assert data["failed"] == 2
        assert data["skipped"] == 1
        assert data["errors"] == 0
        assert data["ai_summary"] == "Test summary"

    def test_report_includes_test_results(self, tmp_path: Path):
        """Test report includes individual test results."""
        test_result = TestResult(
            test_id="test-001",
            test_name="Login Test",
            category="functional",
            result="pass",
            duration_seconds=5.0,
        )

        run_result = RunResult(
            run_id="run-003",
            plan_id="plan-003",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            total_tests=1,
            passed=1,
            test_results=[test_result],
        )

        output_file = tmp_path / "report.json"
        generate_json_report(run_result, [], output_file)

        with open(output_file) as f:
            data = json.load(f)

        assert len(data["test_results"]) == 1
        assert data["test_results"][0]["test_id"] == "test-001"
        assert data["test_results"][0]["test_name"] == "Login Test"

    def test_report_with_nested_data(self, tmp_path: Path):
        """Test report correctly serializes nested data structures."""
        step = StepResult(
            step_index=0,
            action_type="click",
            selector="button",
            status="pass",
        )

        assertion = AssertionResult(
            assertion_type="element_visible",
            selector=".message",
            passed=True,
        )

        evidence = Evidence(
            screenshots=["screenshot1.png"],
            console_logs=["log entry"],
        )

        test_result = TestResult(
            test_id="test-001",
            test_name="Complex Test",
            category="functional",
            result="pass",
            step_results=[step],
            assertion_results=[assertion],
            evidence=evidence,
        )

        run_result = RunResult(
            run_id="run-004",
            plan_id="plan-004",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            total_tests=1,
            passed=1,
            test_results=[test_result],
        )

        output_file = tmp_path / "report.json"
        generate_json_report(run_result, [], output_file)

        with open(output_file) as f:
            data = json.load(f)

        test = data["test_results"][0]
        assert len(test["step_results"]) == 1
        assert len(test["assertion_results"]) == 1
        assert len(test["evidence"]["screenshots"]) == 1

    def test_report_creates_parent_directory(self, tmp_path: Path):
        """Test report creation creates parent directories."""
        output_file = tmp_path / "subdir" / "nested" / "report.json"

        run_result = RunResult(
            run_id="run-005",
            plan_id="plan-005",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
        )

        generate_json_report(run_result, [], output_file)

        assert output_file.exists()
        assert output_file.parent.exists()

    def test_report_is_valid_json(self, tmp_path: Path):
        """Test generated report is valid JSON that can be reloaded."""
        run_result = RunResult(
            run_id="run-006",
            plan_id="plan-006",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            total_tests=5,
            passed=3,
            failed=2,
        )

        output_file = tmp_path / "report.json"
        generate_json_report(run_result, [], output_file)

        # Should be able to reload without errors
        with open(output_file) as f:
            reloaded = json.load(f)

        assert reloaded["run_id"] == "run-006"
        assert isinstance(reloaded, dict)

    def test_report_with_empty_test_results(self, tmp_path: Path):
        """Test report handles empty test results list."""
        run_result = RunResult(
            run_id="run-007",
            plan_id="plan-007",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            test_results=[],
        )

        output_file = tmp_path / "report.json"
        generate_json_report(run_result, [], output_file)

        with open(output_file) as f:
            data = json.load(f)

        assert data["test_results"] == []
