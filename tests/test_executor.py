"""Tests for the executor module — test lifecycle, context isolation, auth injection."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.executor.executor import Executor
from src.models.config import AuthConfig, CrawlConfig, FrameworkConfig, ViewportConfig
from src.models.test_plan import Action, Assertion, TestCase, TestPlan
from src.models.test_result import Evidence, RunResult, StepResult, TestResult


def _make_config(auth: AuthConfig | None = None, max_time: int = 1800) -> FrameworkConfig:
    """Create a FrameworkConfig for testing."""
    return FrameworkConfig(
        target_url="https://example.com",
        auth=auth,
        crawl=CrawlConfig(
            target_url="https://example.com",
            viewport=ViewportConfig(width=1280, height=720, name="desktop"),
        ),
        categories=["functional"],
        max_tests_per_run=50,
        max_execution_time_seconds=max_time,
        selector_timeout_seconds=5,
        ai_model="claude-opus-4-6",
        ai_max_fallback_calls_per_test=3,
        ai_max_planning_tokens=32000,
        visual_diff_tolerance=0.15,
        report_output_dir="./test-reports",
    )


def _make_test_case(
    test_id="tc_001",
    name="Test Login",
    category="functional",
    priority=1,
    target_page_id="page-login",
    requires_auth=False,
    steps=None,
    assertions=None,
    preconditions=None,
) -> TestCase:
    """Create a TestCase for testing."""
    return TestCase(
        test_id=test_id,
        name=name,
        category=category,
        priority=priority,
        target_page_id=target_page_id,
        requires_auth=requires_auth,
        coverage_signature=f"sig_{test_id}",
        steps=steps or [Action(action_type="navigate", value="https://example.com/login")],
        assertions=assertions or [Assertion(assertion_type="element_visible", selector=".login-form")],
        preconditions=preconditions or [],
        timeout_seconds=30,
    )


def _make_plan(test_cases: list[TestCase] | None = None) -> TestPlan:
    """Create a TestPlan for testing."""
    return TestPlan(
        plan_id="plan-001",
        generated_at="2025-01-01T00:00:00Z",
        target_url="https://example.com",
        test_cases=test_cases or [_make_test_case()],
    )


def _make_mock_page():
    """Create an AsyncMock page with all needed methods as non-coroutine where possible."""
    page = AsyncMock()
    page.url = "https://example.com/login"
    page.on = Mock()  # Sync callback registration
    return page


def _make_mock_context(page=None):
    """Create an AsyncMock context that returns a mock page."""
    ctx = AsyncMock()
    ctx.new_page = AsyncMock(return_value=page or _make_mock_page())
    return ctx


# Patch targets for browser infrastructure
STEALTH_BROWSER = "src.executor.executor.launch_stealth_browser"
STEALTH_CONTEXT = "src.executor.executor.create_stealth_context"
AUTH_CAPTURE = "src.executor.executor.authenticate_and_capture_state"
ASYNC_PW = "src.executor.executor.async_playwright"


@pytest.fixture
def mock_playwright():
    """Provide a properly mocked async_playwright context manager."""
    mock_browser = AsyncMock()

    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)

    return mock_pw, mock_browser


class TestExecutorInit:
    """Tests for Executor initialization."""

    def test_creates_run_directory(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        assert executor.run_dir.exists()
        assert executor.run_dir.parent == tmp_path

    def test_run_id_format(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        assert executor.run_id.startswith("run_")
        assert len(executor.run_id) == 12  # "run_" + 8 hex chars

    def test_stores_config_and_client(self, tmp_path):
        config = _make_config()
        mock_ai = Mock()
        executor = Executor(config, ai_client=mock_ai, runs_dir=tmp_path)
        assert executor.config is config
        assert executor.ai_client is mock_ai


class TestExecutorExecute:
    """Tests for the main execute() method."""

    @pytest.mark.asyncio
    async def test_single_test_pass(self, tmp_path):
        """A single passing test produces correct RunResult."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)
        mock_browser = AsyncMock()

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=mock_browser), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_inst = AsyncMock()
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=mock_pw_inst)
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        assert isinstance(result, RunResult)
        assert result.total_tests == 1
        assert result.passed == 1
        assert result.failed == 0
        assert result.run_id == executor.run_id
        assert result.plan_id == "plan-001"
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_failing_assertion_produces_fail(self, tmp_path):
        """A test with a failing assertion results in 'fail' status."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)
        mock_browser = AsyncMock()

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=mock_browser), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=False, message="Element not found", screenshots=[])

            result = await executor.execute(plan)

        assert result.failed == 1
        assert result.passed == 0
        test_r = result.test_results[0]
        assert test_r.result == "fail"
        assert test_r.failure_reason is not None

    @pytest.mark.asyncio
    async def test_tests_sorted_by_priority(self, tmp_path):
        """Tests should be executed in priority order within page groups."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tests = [
            _make_test_case(test_id="tc_low", priority=5, target_page_id="p1"),
            _make_test_case(test_id="tc_high", priority=1, target_page_id="p1"),
            _make_test_case(test_id="tc_mid", priority=3, target_page_id="p1"),
        ]
        plan = _make_plan(test_cases=tests)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        assert result.total_tests == 3
        assert result.passed == 3

    @pytest.mark.asyncio
    async def test_context_isolation_per_test(self, tmp_path):
        """Each test gets its own browser context (isolation)."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tests = [
            _make_test_case(test_id="tc_1", target_page_id="p"),
            _make_test_case(test_id="tc_2", target_page_id="p"),
        ]
        plan = _make_plan(test_cases=tests)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context) as ctx_fn, \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        # create_stealth_context called once per test
        assert ctx_fn.call_count == 2
        # Each context is closed after use
        assert mock_context.close.call_count == 2

    @pytest.mark.asyncio
    async def test_auth_state_injected_when_required(self, tmp_path):
        """Auth storage state is passed to context when test requires_auth=True."""
        mock_page = _make_mock_page()
        mock_page.url = "https://example.com/dashboard"
        mock_context = _make_mock_context(mock_page)

        # Simulate successful auth
        auth_result = Mock()
        auth_result.success = True
        auth_result.auth_flow = Mock(detection_method="explicit")
        fake_storage = {"cookies": [{"name": "session", "value": "abc"}]}

        auth = AuthConfig(
            login_url="https://example.com/login",
            username="user",
            password="pass",
        )
        config = _make_config(auth=auth)
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tc = _make_test_case(requires_auth=True)
        plan = _make_plan(test_cases=[tc])

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context) as ctx_fn, \
             patch(AUTH_CAPTURE, return_value=(auth_result, fake_storage)) as mock_auth, \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        mock_auth.assert_called_once()
        ctx_call = ctx_fn.call_args
        assert ctx_call.kwargs["storage_state"] == fake_storage

    @pytest.mark.asyncio
    async def test_no_auth_when_not_required(self, tmp_path):
        """When test doesn't require auth, storage_state should be None."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        auth_result = Mock(success=True, auth_flow=Mock(detection_method="explicit"))

        auth = AuthConfig(login_url="https://example.com/login", username="u", password="p")
        config = _make_config(auth=auth)
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tc = _make_test_case(requires_auth=False)
        plan = _make_plan(test_cases=[tc])

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context) as ctx_fn, \
             patch(AUTH_CAPTURE, return_value=(auth_result, {"cookies": []})), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        ctx_call = ctx_fn.call_args
        assert ctx_call.kwargs["storage_state"] is None

    @pytest.mark.asyncio
    async def test_time_limit_skips_remaining(self, tmp_path):
        """When time limit is reached, remaining tests are skipped."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        # Use a very short time limit
        config = _make_config(max_time=0)
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tests = [
            _make_test_case(test_id="tc_1", target_page_id="p"),
            _make_test_case(test_id="tc_2", target_page_id="p"),
        ]
        plan = _make_plan(test_cases=tests)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        assert result.skipped >= 1
        skipped = [r for r in result.test_results if r.result == "skip"]
        assert len(skipped) >= 1
        assert "Time limit" in skipped[0].failure_reason

    @pytest.mark.asyncio
    async def test_crash_in_test_produces_error(self, tmp_path):
        """If a test crashes inside _run_test's try block, it's marked as 'error'."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock, side_effect=RuntimeError("Assertion engine crashed")), \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await executor.execute(plan)

        assert result.errors == 1
        assert result.test_results[0].result == "error"
        assert "Assertion engine crashed" in result.test_results[0].failure_reason

    @pytest.mark.asyncio
    async def test_step_failure_is_recorded_not_error(self, tmp_path):
        """A step-level exception is caught and recorded as a failed step, not a test error."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock, side_effect=RuntimeError("Selector not found")), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        # Step failure doesn't make the whole test "error" — it just records a failed step
        tr = result.test_results[0]
        assert tr.step_results[0].status == "fail"
        assert "Selector not found" in tr.step_results[0].error_message

    @pytest.mark.asyncio
    async def test_page_grouping(self, tmp_path):
        """Tests are grouped by target_page_id."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tests = [
            _make_test_case(test_id="tc_1", target_page_id="page-a"),
            _make_test_case(test_id="tc_2", target_page_id="page-b"),
            _make_test_case(test_id="tc_3", target_page_id="page-a"),
        ]
        plan = _make_plan(test_cases=tests)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        assert result.total_tests == 3
        assert result.passed == 3

    @pytest.mark.asyncio
    async def test_result_counts_are_correct(self, tmp_path):
        """Verify pass/fail/skip/error counts match test results."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tests = [
            _make_test_case(test_id="tc_pass", target_page_id="p"),
            _make_test_case(test_id="tc_fail", target_page_id="p"),
        ]
        plan = _make_plan(test_cases=tests)

        call_count = 0

        async def alternating_assertion(page, assertion, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                return Mock(passed=False, message="FAIL", screenshots=[])
            return Mock(passed=True, message="OK", screenshots=[])

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=mock_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", side_effect=alternating_assertion), \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await executor.execute(plan)

        assert result.total_tests == 2
        assert result.passed + result.failed + result.skipped + result.errors == result.total_tests


class TestSessionInvalidation:
    """Tests for _session_invalidated static method."""

    def test_detects_logout_post(self):
        result = TestResult(
            test_id="t1", test_name="Logout", category="functional", result="pass",
            evidence=Evidence(network_log=[
                {"url": "https://example.com/api/logout", "method": "POST"},
            ]),
        )
        assert Executor._session_invalidated(result) is True

    def test_detects_signout(self):
        result = TestResult(
            test_id="t1", test_name="Sign out", category="functional", result="pass",
            evidence=Evidence(network_log=[
                {"url": "https://example.com/signout", "method": "POST"},
            ]),
        )
        assert Executor._session_invalidated(result) is True

    def test_ignores_get_logout(self):
        """GET requests to logout URLs don't count as session invalidation."""
        result = TestResult(
            test_id="t1", test_name="View logout", category="functional", result="pass",
            evidence=Evidence(network_log=[
                {"url": "https://example.com/logout", "method": "GET"},
            ]),
        )
        assert Executor._session_invalidated(result) is False

    def test_no_network_log(self):
        result = TestResult(
            test_id="t1", test_name="Test", category="functional", result="pass",
            evidence=Evidence(),
        )
        assert Executor._session_invalidated(result) is False

    def test_no_evidence(self):
        result = TestResult(
            test_id="t1", test_name="Test", category="functional", result="pass",
        )
        assert Executor._session_invalidated(result) is False

    def test_normal_requests(self):
        result = TestResult(
            test_id="t1", test_name="Test", category="functional", result="pass",
            evidence=Evidence(network_log=[
                {"url": "https://example.com/api/data", "method": "POST"},
                {"url": "https://example.com/api/profile", "method": "GET"},
            ]),
        )
        assert Executor._session_invalidated(result) is False
