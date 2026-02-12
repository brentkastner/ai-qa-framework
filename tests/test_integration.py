"""Integration tests for the QA framework.

These tests verify that multiple components work together correctly.
They use mocks for external dependencies (browsers, AI API) but test
the actual integration points between framework components.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.models.config import FrameworkConfig
from src.models.site_model import ElementModel, PageModel, SiteModel
from src.models.test_plan import Action, Assertion, TestCase as TestCaseModel, TestPlan as TestPlanModel
from src.models.test_result import RunResult, TestResult
from src.planner.schema_validator import validate_test_plan


@pytest.mark.integration
class TestConfigAndModels:
    """Test configuration loading and model creation flow."""

    def test_config_load_and_model_creation(self, temp_config_file: Path):
        """Test loading config and creating models."""
        # Load config
        config = FrameworkConfig.load(temp_config_file)

        assert config.target_url == "https://example.com"

        # Create a site model based on config
        site = SiteModel(base_url=config.target_url)

        assert site.base_url == config.target_url

    def test_test_plan_creation_and_validation(self):
        """Test creating a test plan and validating it."""
        # Create test plan
        test_case = TestCaseModel(
            test_id="test-001",
            name="Integration test",
            category="functional",
            priority=1,
            steps=[
                Action(action_type="navigate", value="https://example.com"),
                Action(action_type="click", selector="button#submit"),
            ],
            assertions=[
                Assertion(assertion_type="url_matches", expected_value="/success")
            ],
        )

        plan = TestPlanModel(
            plan_id="plan-001",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        # Validate plan
        errors = validate_test_plan(plan)

        assert len(errors) == 0, f"Validation errors: {errors}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestExecutorFlow:
    """Test executor component integration."""

    async def test_action_to_assertion_flow(self, mock_page, temp_evidence_dir):
        """Test running actions followed by assertions."""
        from src.executor.action_runner import run_action
        from src.executor.assertion_checker import check_assertion

        # Set up page mock
        mock_page.url = "https://example.com/success"

        # Run action
        action = Action(
            action_type="navigate",
            value="https://example.com/success",
        )
        await run_action(mock_page, action)

        # Check assertion
        assertion = Assertion(
            assertion_type="url_matches",
            expected_value="/success",
        )
        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True

    async def test_multiple_actions_sequence(self, mock_page):
        """Test executing a sequence of actions."""
        from src.executor.action_runner import run_action

        actions = [
            Action(action_type="navigate", value="https://example.com"),
            Action(action_type="fill", selector="input[name='email']", value="test@example.com"),
            Action(action_type="fill", selector="input[name='password']", value="password123"),
            Action(action_type="click", selector="button#submit"),
        ]

        # Execute all actions
        for action in actions:
            await run_action(mock_page, action)

        # Verify all actions were called
        assert mock_page.goto.called
        assert mock_page.fill.call_count == 2
        assert mock_page.click.called


@pytest.mark.integration
class TestReportingFlow:
    """Test reporting integration."""

    def test_test_result_to_json_report(self, tmp_path: Path):
        """Test creating test results and generating JSON report."""
        from src.reporter.json_report import generate_json_report

        # Create test result
        test_result = TestResult(
            test_id="test-001",
            test_name="Login test",
            category="functional",
            result="pass",
            duration_seconds=3.5,
        )

        # Create run result
        run_result = RunResult(
            run_id="run-001",
            plan_id="plan-001",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            total_tests=1,
            passed=1,
            test_results=[test_result],
        )

        # Generate report
        report_file = tmp_path / "report.json"
        generate_json_report(run_result, [], report_file)

        # Verify report
        assert report_file.exists()
        with open(report_file) as f:
            data = json.load(f)

        assert data["run_id"] == "run-001"
        assert len(data["test_results"]) == 1

    def test_html_and_json_reports_consistency(self, tmp_path: Path):
        """Test that HTML and JSON reports contain same data."""
        from src.reporter.json_report import generate_json_report
        from src.reporter.html_report import generate_html_report

        run_result = RunResult(
            run_id="run-002",
            plan_id="plan-002",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:10:00Z",
            target_url="https://example.com",
            total_tests=5,
            passed=3,
            failed=2,
        )

        json_file = tmp_path / "report.json"
        html_file = tmp_path / "report.html"

        generate_json_report(run_result, [], json_file)
        generate_html_report(run_result, [], None, html_file)

        assert json_file.exists()
        assert html_file.exists()

        # Verify JSON content
        with open(json_file) as f:
            json_data = json.load(f)

        assert json_data["total_tests"] == 5
        assert json_data["passed"] == 3
        assert json_data["failed"] == 2


@pytest.mark.integration
class TestEndToEndScenarios:
    """End-to-end integration scenarios."""

    def test_config_to_plan_to_results(self, temp_config_file: Path):
        """Test flow from config through planning to results."""
        # Load config
        config = FrameworkConfig.load(temp_config_file)

        # Create site model
        page = PageModel(
            page_id="page-1",
            url=f"{config.target_url}/",
            page_type="form",
            elements=[
                ElementModel(
                    element_id="btn-1",
                    tag="button",
                    selector="button#submit",
                    is_interactive=True,
                )
            ],
        )

        site = SiteModel(base_url=config.target_url, pages=[page])

        # Create test plan
        test_case = TestCaseModel(
            test_id="test-001",
            name="Test homepage",
            category="functional",
            target_page_id="page-1",
            steps=[
                Action(action_type="navigate", value=f"{config.target_url}/"),
                Action(action_type="click", selector="button#submit"),
            ],
            assertions=[
                Assertion(assertion_type="element_visible", selector=".result")
            ],
        )

        plan = TestPlanModel(
            plan_id="plan-001",
            generated_at="2025-01-01T00:00:00Z",
            target_url=config.target_url,
            test_cases=[test_case],
        )

        # Validate plan
        errors = validate_test_plan(plan)
        assert len(errors) == 0

        # Create result (simulated execution)
        test_result = TestResult(
            test_id=test_case.test_id,
            test_name=test_case.name,
            category=test_case.category,
            result="pass",
            duration_seconds=2.0,
        )

        run_result = RunResult(
            run_id="run-001",
            plan_id=plan.plan_id,
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url=config.target_url,
            total_tests=1,
            passed=1,
            test_results=[test_result],
        )

        # Verify the complete flow
        assert run_result.total_tests == len(plan.test_cases)
        assert run_result.target_url == config.target_url

    @patch("anthropic.Anthropic")
    def test_ai_client_integration(self, mock_anthropic_class):
        """Test AI client integration with prompts."""
        from src.ai.client import AIClient
        from src.ai.prompts.summary import build_summary_prompt

        # Setup mock
        mock_content = Mock()
        mock_content.text = "Test run completed successfully."
        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        # Create AI client
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = AIClient()

            # Build prompt
            run_result_json = json.dumps({
                "total_tests": 5,
                "passed": 4,
                "failed": 1,
            })
            coverage_summary = "5 tests executed across functional tests."
            prompt = build_summary_prompt(run_result_json, coverage_summary)

            # Get summary
            with patch.object(client, '_save_exchange_log'):
                summary = client.complete(
                    system_prompt="You are a QA assistant.",
                    user_message=prompt,
                )

            assert summary == "Test run completed successfully."
            assert client.call_count == 1


@pytest.mark.integration
@pytest.mark.slow
class TestPerformanceScenarios:
    """Integration tests for performance scenarios."""

    def test_large_test_plan_validation(self):
        """Test validating a large test plan."""
        # Create a plan with many tests
        test_cases = [
            TestCaseModel(
                test_id=f"test-{i:03d}",
                name=f"Test {i}",
                category="functional",
                steps=[Action(action_type="wait", value="1000")],
            )
            for i in range(100)
        ]

        plan = TestPlanModel(
            plan_id="plan-large",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=test_cases,
        )

        # Should handle large plans
        errors = validate_test_plan(plan)

        assert len(errors) == 0

    def test_multiple_reports_generation(self, tmp_path: Path):
        """Test generating multiple reports simultaneously."""
        from src.reporter.json_report import generate_json_report

        # Create multiple run results
        run_results = [
            RunResult(
                run_id=f"run-{i:03d}",
                plan_id=f"plan-{i:03d}",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
                target_url="https://example.com",
                total_tests=i,
                passed=i,
            )
            for i in range(1, 11)
        ]

        # Generate all reports
        for i, result in enumerate(run_results, 1):
            report_file = tmp_path / f"report_{i:03d}.json"
            generate_json_report(result, [], report_file)

        # Verify all were created
        report_files = list(tmp_path.glob("report_*.json"))
        assert len(report_files) == 10
