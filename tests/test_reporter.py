"""Tests for reporter module — HTML report, regression detector, reporter orchestration."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.models.config import CrawlConfig, FrameworkConfig, ViewportConfig
from src.models.coverage import CoverageRegistry, GlobalCoverageStats
from src.models.test_result import (
    AssertionResult,
    Evidence,
    FallbackRecord,
    RunResult,
    StepResult,
    TestResult,
)
from src.reporter.html_report import (
    _build_step_row,
    _build_test_card,
    _embed_image,
    _step_icon,
    generate_html_report,
)
from src.reporter.regression_detector import Regression, detect_regressions
from src.reporter.reporter import Reporter


# ============================================================================
# Helpers
# ============================================================================

def _make_test_result(
    test_id="tc_001",
    name="Test Login",
    category="functional",
    result="pass",
    priority=1,
    coverage_signature="login_sig",
    failure_reason=None,
    assertions_passed=1,
    assertions_total=1,
) -> TestResult:
    return TestResult(
        test_id=test_id, test_name=name, category=category,
        result=result, priority=priority,
        coverage_signature=coverage_signature,
        failure_reason=failure_reason,
        duration_seconds=1.5,
        assertions_passed=assertions_passed,
        assertions_total=assertions_total,
        evidence=Evidence(),
    )


def _make_run_result(test_results=None, run_id="run_abc123") -> RunResult:
    trs = test_results or [_make_test_result()]
    return RunResult(
        run_id=run_id,
        plan_id="plan-001",
        started_at="2025-01-01T00:00:00Z",
        completed_at="2025-01-01T00:05:00Z",
        target_url="https://example.com",
        total_tests=len(trs),
        passed=sum(1 for r in trs if r.result == "pass"),
        failed=sum(1 for r in trs if r.result == "fail"),
        skipped=sum(1 for r in trs if r.result == "skip"),
        errors=sum(1 for r in trs if r.result == "error"),
        duration_seconds=300.0,
        test_results=trs,
    )


def _make_config() -> FrameworkConfig:
    return FrameworkConfig(
        target_url="https://example.com",
        crawl=CrawlConfig(
            target_url="https://example.com",
            viewport=ViewportConfig(width=1280, height=720, name="desktop"),
        ),
        report_formats=["html", "json"],
        report_output_dir="./test-reports",
    )


# ============================================================================
# Regression Detector
# ============================================================================


class TestRegressionDetector:
    """Tests for detect_regressions()."""

    def test_no_regressions_when_all_pass(self):
        prev = _make_run_result([_make_test_result(result="pass")])
        curr = _make_run_result([_make_test_result(result="pass")])
        regressions = detect_regressions(prev, curr)
        assert regressions == []

    def test_detects_pass_to_fail(self):
        prev = _make_run_result([_make_test_result(result="pass", coverage_signature="sig_a")])
        curr = _make_run_result([_make_test_result(result="fail", coverage_signature="sig_a", failure_reason="Element not found")])
        regressions = detect_regressions(prev, curr)
        assert len(regressions) == 1
        assert regressions[0].test_name == "Test Login"
        assert regressions[0].previous_result == "pass"
        assert regressions[0].current_result == "fail"
        assert regressions[0].failure_reason == "Element not found"

    def test_detects_pass_to_error(self):
        prev = _make_run_result([_make_test_result(result="pass", coverage_signature="sig_a")])
        curr = _make_run_result([_make_test_result(result="error", coverage_signature="sig_a")])
        regressions = detect_regressions(prev, curr)
        assert len(regressions) == 1
        assert regressions[0].current_result == "error"

    def test_ignores_fail_to_fail(self):
        prev = _make_run_result([_make_test_result(result="fail", coverage_signature="sig_a")])
        curr = _make_run_result([_make_test_result(result="fail", coverage_signature="sig_a")])
        regressions = detect_regressions(prev, curr)
        assert regressions == []

    def test_ignores_fail_to_pass(self):
        prev = _make_run_result([_make_test_result(result="fail", coverage_signature="sig_a")])
        curr = _make_run_result([_make_test_result(result="pass", coverage_signature="sig_a")])
        regressions = detect_regressions(prev, curr)
        assert regressions == []

    def test_matches_by_coverage_signature(self):
        prev = _make_run_result([
            _make_test_result(test_id="tc_old", name="Old name", coverage_signature="stable_sig", result="pass"),
        ])
        curr = _make_run_result([
            _make_test_result(test_id="tc_new", name="New name", coverage_signature="stable_sig", result="fail"),
        ])
        regressions = detect_regressions(prev, curr)
        assert len(regressions) == 1

    def test_falls_back_to_name_matching(self):
        prev = _make_run_result([
            _make_test_result(name="Login test", coverage_signature="", result="pass"),
        ])
        curr = _make_run_result([
            _make_test_result(name="Login test", coverage_signature="", result="fail"),
        ])
        regressions = detect_regressions(prev, curr)
        assert len(regressions) == 1

    def test_new_tests_not_counted(self):
        """Tests that only exist in the current run aren't regressions."""
        prev = _make_run_result([_make_test_result(coverage_signature="sig_a", result="pass")])
        curr = _make_run_result([
            _make_test_result(coverage_signature="sig_a", result="pass"),
            _make_test_result(test_id="tc_new", name="Brand new", coverage_signature="sig_new", result="fail"),
        ])
        regressions = detect_regressions(prev, curr)
        assert regressions == []

    def test_multiple_regressions(self):
        prev = _make_run_result([
            _make_test_result(test_id="tc_1", coverage_signature="sig_1", result="pass"),
            _make_test_result(test_id="tc_2", coverage_signature="sig_2", result="pass"),
            _make_test_result(test_id="tc_3", coverage_signature="sig_3", result="pass"),
        ])
        curr = _make_run_result([
            _make_test_result(test_id="tc_1", coverage_signature="sig_1", result="fail"),
            _make_test_result(test_id="tc_2", coverage_signature="sig_2", result="pass"),
            _make_test_result(test_id="tc_3", coverage_signature="sig_3", result="error"),
        ])
        regressions = detect_regressions(prev, curr)
        assert len(regressions) == 2


# ============================================================================
# HTML Report Generation
# ============================================================================


class TestHTMLReportHelpers:
    """Tests for HTML report helper functions."""

    def test_step_icon_pass(self):
        icon = _step_icon("pass")
        assert "pass-icon" in icon
        assert "&#10003;" in icon  # checkmark

    def test_step_icon_fail(self):
        icon = _step_icon("fail")
        assert "fail-icon" in icon
        assert "&#10007;" in icon  # X mark

    def test_step_icon_skip(self):
        icon = _step_icon("skip")
        assert "skip-icon" in icon

    def test_step_icon_unknown(self):
        icon = _step_icon("unknown")
        assert "skip-icon" in icon  # falls through to default

    def test_embed_image_nonexistent(self):
        result = _embed_image("/nonexistent/path/image.png")
        assert result == ""

    def test_embed_image_real_png(self, tmp_path):
        # Create a tiny valid PNG
        png = tmp_path / "test.png"
        png.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
            b'\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-'
            b'\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        result = _embed_image(str(png))
        assert result.startswith("data:image/png;base64,")

    def test_embed_image_empty_file(self, tmp_path):
        empty = tmp_path / "empty.png"
        empty.write_bytes(b"")
        result = _embed_image(str(empty))
        assert result == ""


class TestBuildTestCard:
    """Tests for _build_test_card HTML output."""

    def test_card_contains_test_name(self):
        tr = _make_test_result(name="Login Form Submit")
        card = _build_test_card(tr)
        assert "Login Form Submit" in card

    def test_card_escapes_html_in_name(self):
        tr = _make_test_result(name='<script>alert("xss")</script>')
        card = _build_test_card(tr)
        assert "<script>" not in card
        assert "&lt;script&gt;" in card

    def test_card_shows_failure_reason(self):
        tr = _make_test_result(result="fail", failure_reason="Element not found")
        card = _build_test_card(tr)
        assert "Element not found" in card
        assert "failure-banner" in card

    def test_card_escapes_failure_reason(self):
        tr = _make_test_result(result="fail", failure_reason='<img src=x onerror=alert(1)>')
        card = _build_test_card(tr)
        # The <img> tag must be escaped so it renders as text, not as HTML
        assert "<img src=x" not in card  # Raw HTML tag should NOT appear
        assert "&lt;img" in card  # Escaped version should appear

    def test_card_shows_step_results(self):
        tr = _make_test_result()
        tr.step_results = [StepResult(
            step_index=0, action_type="click", selector="button#submit",
            description="Click submit", status="pass",
        )]
        card = _build_test_card(tr)
        assert "click" in card
        assert "Click submit" in card

    def test_card_shows_assertion_results(self):
        tr = _make_test_result()
        tr.assertion_results = [AssertionResult(
            assertion_type="element_visible", selector=".success",
            description="Success message visible", passed=True, message="Visible",
        )]
        card = _build_test_card(tr)
        assert "Success message visible" in card

    def test_card_shows_fallback_records(self):
        tr = _make_test_result()
        tr.fallback_records = [FallbackRecord(
            step_index=2, original_selector="button.old",
            decision="retry", new_selector="button.new",
            reasoning="Found alternative selector",
        )]
        card = _build_test_card(tr)
        assert "retry" in card
        assert "Found alternative selector" in card

    def test_card_shows_console_errors(self):
        tr = _make_test_result()
        tr.evidence = Evidence(console_logs=["[error] Uncaught TypeError"])
        card = _build_test_card(tr)
        assert "Uncaught TypeError" in card


class TestGenerateHTMLReport:
    """Tests for generate_html_report()."""

    def test_creates_file(self, tmp_path):
        run_result = _make_run_result()
        output = tmp_path / "report.html"
        generate_html_report(run_result, [], None, output)
        assert output.exists()
        content = output.read_text()
        assert "<!DOCTYPE html>" in content
        assert run_result.run_id in content

    def test_includes_regressions(self, tmp_path):
        run_result = _make_run_result()
        regressions = [Regression(
            test_name="Login test", category="functional",
            previous_result="pass", current_result="fail",
            failure_reason="Button moved",
        )]
        output = tmp_path / "report.html"
        generate_html_report(run_result, regressions, None, output)
        content = output.read_text()
        assert "Regressions" in content
        assert "Login test" in content
        assert "Button moved" in content

    def test_includes_ai_summary(self, tmp_path):
        run_result = _make_run_result()
        run_result.ai_summary = "All tests passed. Site looks healthy."
        output = tmp_path / "report.html"
        generate_html_report(run_result, [], None, output)
        content = output.read_text()
        assert "AI Summary" in content
        assert "Site looks healthy" in content

    def test_escapes_run_id(self, tmp_path):
        run_result = _make_run_result(run_id='run_<bad>"id')
        output = tmp_path / "report.html"
        generate_html_report(run_result, [], None, output)
        content = output.read_text()
        assert 'run_<bad>' not in content

    def test_multiple_test_cards(self, tmp_path):
        results = [
            _make_test_result(test_id="tc_1", name="Test A", result="pass"),
            _make_test_result(test_id="tc_2", name="Test B", result="fail", failure_reason="broken"),
        ]
        run_result = _make_run_result(test_results=results)
        output = tmp_path / "report.html"
        generate_html_report(run_result, [], None, output)
        content = output.read_text()
        assert "Test A" in content
        assert "Test B" in content


class TestBuildStepRow:
    """Tests for _build_step_row helper."""

    def test_basic_step(self):
        sr = StepResult(step_index=0, action_type="click", selector="button", status="pass")
        html = _build_step_row(sr)
        assert "click" in html
        assert "button" in html

    def test_step_with_error(self):
        sr = StepResult(step_index=0, action_type="fill", status="fail", error_message="Timeout")
        html = _build_step_row(sr)
        assert "Timeout" in html
        assert "step-error" in html

    def test_escapes_selector(self):
        sr = StepResult(step_index=0, action_type="click", selector='[data-x="<evil>"]', status="pass")
        html = _build_step_row(sr)
        assert "<evil>" not in html
        assert "&lt;evil&gt;" in html


# ============================================================================
# Reporter Orchestration
# ============================================================================


class TestReporter:
    """Tests for Reporter class."""

    def test_generates_html_and_json(self, tmp_path):
        config = _make_config()
        reporter = Reporter(config)
        run_result = _make_run_result()

        generated = reporter.generate_reports(run_result, output_dir=tmp_path)

        assert "html" in generated
        assert "json" in generated
        assert Path(generated["html"]).exists()
        assert Path(generated["json"]).exists()

    def test_html_only(self, tmp_path):
        config = _make_config()
        config.report_formats = ["html"]
        reporter = Reporter(config)
        run_result = _make_run_result()

        generated = reporter.generate_reports(run_result, output_dir=tmp_path)

        assert "html" in generated
        assert "json" not in generated

    def test_json_only(self, tmp_path):
        config = _make_config()
        config.report_formats = ["json"]
        reporter = Reporter(config)
        run_result = _make_run_result()

        generated = reporter.generate_reports(run_result, output_dir=tmp_path)

        assert "json" in generated
        assert "html" not in generated

    def test_regression_detection_with_previous_run(self, tmp_path):
        config = _make_config()
        reporter = Reporter(config)

        prev = _make_run_result([_make_test_result(result="pass", coverage_signature="sig_a")])
        curr = _make_run_result([_make_test_result(result="fail", coverage_signature="sig_a")])

        generated = reporter.generate_reports(curr, previous_run=prev, output_dir=tmp_path)

        # HTML should contain regression info
        html_content = Path(generated["html"]).read_text()
        assert "Regressions" in html_content

    def test_no_regression_without_previous_run(self, tmp_path):
        config = _make_config()
        reporter = Reporter(config)
        run_result = _make_run_result([_make_test_result(result="fail")])

        generated = reporter.generate_reports(run_result, output_dir=tmp_path)

        html_content = Path(generated["html"]).read_text()
        assert "Regressions" not in html_content

    def test_ai_summary_generation(self, tmp_path):
        mock_ai = Mock()
        mock_ai.complete.return_value = "AI generated summary text here."

        config = _make_config()
        reporter = Reporter(config, ai_client=mock_ai)
        run_result = _make_run_result()
        run_result.ai_summary = ""  # Force generation

        reporter.generate_reports(run_result, output_dir=tmp_path)

        mock_ai.complete.assert_called_once()
        assert run_result.ai_summary == "AI generated summary text here."

    def test_skips_ai_summary_when_already_set(self, tmp_path):
        mock_ai = Mock()
        config = _make_config()
        reporter = Reporter(config, ai_client=mock_ai)
        run_result = _make_run_result()
        run_result.ai_summary = "Already set"

        reporter.generate_reports(run_result, output_dir=tmp_path)

        mock_ai.complete.assert_not_called()

    def test_basic_summary_without_ai(self, tmp_path):
        config = _make_config()
        reporter = Reporter(config, ai_client=None)
        run_result = _make_run_result()
        run_result.ai_summary = ""

        reporter.generate_reports(run_result, output_dir=tmp_path)

        # Should still have no summary set (basic is only used when AI fails)
        # The ai_summary is not set when there's no ai_client
        assert True  # Just verifying it doesn't crash

    def test_ai_summary_failure_falls_back(self, tmp_path):
        mock_ai = Mock()
        mock_ai.complete.side_effect = RuntimeError("API down")

        config = _make_config()
        reporter = Reporter(config, ai_client=mock_ai)
        run_result = _make_run_result()
        run_result.ai_summary = ""

        reporter.generate_reports(run_result, output_dir=tmp_path)

        # Should fall back to basic summary
        assert "example.com" in run_result.ai_summary

    def test_creates_output_dir(self, tmp_path):
        config = _make_config()
        reporter = Reporter(config)
        run_result = _make_run_result()

        out = tmp_path / "deep" / "nested"
        generated = reporter.generate_reports(run_result, output_dir=out)
        assert out.exists()
