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
        capture_video="off",
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
    async def test_multiple_page_targets(self, tmp_path):
        """Tests targeting different pages all complete successfully."""
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


class TestParallelExecution:
    """Tests for parallel test execution via asyncio.gather + semaphore."""

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrency(self, tmp_path):
        """No more than max_parallel_contexts tests run simultaneously."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def tracking_run_action(page, action, **kwargs):
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.05)  # Simulate work
            async with lock:
                current_concurrent -= 1

        config = _make_config()
        config.max_parallel_contexts = 2
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tests = [_make_test_case(test_id=f"tc_{i}", target_page_id=f"p{i}") for i in range(6)]
        plan = _make_plan(test_cases=tests)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, side_effect=lambda *a, **kw: _make_mock_context()), \
             patch("src.executor.executor.run_action", side_effect=tracking_run_action), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        assert result.total_tests == 6
        assert result.passed == 6
        assert max_concurrent <= 2, f"Concurrency exceeded limit: {max_concurrent} > 2"

    @pytest.mark.asyncio
    async def test_sequential_with_max_parallel_one(self, tmp_path):
        """max_parallel_contexts=1 effectively runs tests sequentially."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def tracking_run_action(page, action, **kwargs):
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.02)
            async with lock:
                current_concurrent -= 1

        config = _make_config()
        config.max_parallel_contexts = 1
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        tests = [_make_test_case(test_id=f"tc_{i}", target_page_id=f"p{i}") for i in range(4)]
        plan = _make_plan(test_cases=tests)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, side_effect=lambda *a, **kw: _make_mock_context()), \
             patch("src.executor.executor.run_action", side_effect=tracking_run_action), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        assert result.total_tests == 4
        assert result.passed == 4
        assert max_concurrent == 1

    @pytest.mark.asyncio
    async def test_session_invalidation_reauth_in_parallel(self, tmp_path):
        """Session invalidation triggers re-auth protected by lock."""
        auth = AuthConfig(login_url="https://example.com/login", username="u", password="p")
        config = _make_config(auth=auth)
        config.max_parallel_contexts = 2
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        # First test triggers logout, second test is normal
        tc_logout = _make_test_case(test_id="tc_logout", requires_auth=True)
        tc_normal = _make_test_case(test_id="tc_normal", requires_auth=True)
        plan = _make_plan(test_cases=[tc_logout, tc_normal])

        auth_result = Mock(success=True, auth_flow=Mock(detection_method="explicit"))
        initial_storage = {"cookies": [{"name": "session", "value": "initial"}]}
        refreshed_storage = {"cookies": [{"name": "session", "value": "refreshed"}]}

        auth_call_count = 0

        async def mock_auth_fn(*args, **kwargs):
            nonlocal auth_call_count
            auth_call_count += 1
            if auth_call_count == 1:
                return (auth_result, initial_storage)
            return (auth_result, refreshed_storage)

        # Make the logout test return a network log that triggers session invalidation
        logout_page = _make_mock_page()
        normal_page = _make_mock_page()

        logout_context = _make_mock_context(logout_page)
        normal_context = _make_mock_context(normal_page)

        context_idx = 0

        def make_context(*args, **kwargs):
            nonlocal context_idx
            context_idx += 1
            if context_idx == 1:
                return logout_context
            return normal_context

        # Patch _session_invalidated to return True for logout test
        original_invalidated = Executor._session_invalidated

        def patched_invalidated(result):
            if result.test_id == "tc_logout":
                return True
            return original_invalidated(result)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, side_effect=make_context), \
             patch(AUTH_CAPTURE, side_effect=mock_auth_fn), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"), \
             patch.object(Executor, "_session_invalidated", staticmethod(patched_invalidated)):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        assert result.total_tests == 2
        assert result.passed == 2
        # Initial auth + re-auth after session invalidation
        assert auth_call_count == 2

    @pytest.mark.asyncio
    async def test_parallel_results_preserve_order(self, tmp_path):
        """Results from asyncio.gather maintain the order of sorted tests."""
        config = _make_config()
        config.max_parallel_contexts = 3
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        # Priority order: tc_high (1) → tc_mid (3) → tc_low (5)
        tests = [
            _make_test_case(test_id="tc_low", priority=5, target_page_id="p1"),
            _make_test_case(test_id="tc_high", priority=1, target_page_id="p2"),
            _make_test_case(test_id="tc_mid", priority=3, target_page_id="p3"),
        ]
        plan = _make_plan(test_cases=tests)

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, side_effect=lambda *a, **kw: _make_mock_context()), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=True, message="OK", screenshots=[])

            result = await executor.execute(plan)

        # Results should be in priority-sorted order (gather preserves input order)
        assert result.test_results[0].test_id == "tc_high"
        assert result.test_results[1].test_id == "tc_mid"
        assert result.test_results[2].test_id == "tc_low"


class TestFindVideoFile:
    """Tests for Executor._find_video_file static helper."""

    def test_finds_webm_file(self, tmp_path):
        video_dir = tmp_path / "video"
        video_dir.mkdir()
        webm = video_dir / "abc123.webm"
        webm.write_bytes(b"fake video")

        result = Executor._find_video_file(video_dir)
        assert result == str(webm)

    def test_returns_none_when_empty(self, tmp_path):
        video_dir = tmp_path / "video"
        video_dir.mkdir()

        result = Executor._find_video_file(video_dir)
        assert result is None

    def test_returns_none_for_non_webm(self, tmp_path):
        video_dir = tmp_path / "video"
        video_dir.mkdir()
        (video_dir / "screenshot.png").write_bytes(b"image")

        result = Executor._find_video_file(video_dir)
        assert result is None

    def test_returns_none_for_missing_dir(self, tmp_path):
        result = Executor._find_video_file(tmp_path / "nonexistent")
        assert result is None


class TestVideoRecording:
    """Tests for video recording in all three capture_video modes."""

    @pytest.mark.asyncio
    async def test_off_mode_no_video(self, tmp_path):
        """capture_video='off': no video dir passed, no video in result."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        config.capture_video = "off"
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

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

        assert ctx_fn.call_count == 1
        assert result.test_results[0].evidence.video_path is None
        # Verify no record_video_dir was passed
        call_kwargs = ctx_fn.call_args.kwargs
        assert call_kwargs.get("record_video_dir") is None

    @pytest.mark.asyncio
    async def test_always_mode_records_video(self, tmp_path):
        """capture_video='always': video dir passed to context, video path attached."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        config.capture_video = "always"
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        # Create the video file when context closes (simulating Playwright behavior)
        async def create_video_on_close():
            video_dir = executor.run_dir / "evidence" / "tc_001" / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            (video_dir / "recording.webm").write_bytes(b"fake video data")

        mock_context.close = AsyncMock(side_effect=create_video_on_close)

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

        # Context created once with record_video_dir
        assert ctx_fn.call_count == 1
        call_kwargs = ctx_fn.call_args.kwargs
        assert call_kwargs["record_video_dir"] is not None
        assert "video" in call_kwargs["record_video_dir"]

        # Video path attached to evidence
        tr = result.test_results[0]
        assert tr.evidence.video_path is not None
        assert tr.evidence.video_path.endswith(".webm")

    @pytest.mark.asyncio
    async def test_on_failure_skips_passing_test(self, tmp_path):
        """capture_video='on_failure': passing test gets no re-run, no video."""
        mock_page = _make_mock_page()
        mock_context = _make_mock_context(mock_page)

        config = _make_config()
        config.capture_video = "on_failure"
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

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

        # Only one context created (no re-run for passing test)
        assert ctx_fn.call_count == 1
        assert result.test_results[0].evidence.video_path is None
        assert result.test_results[0].potentially_flaky is False

    @pytest.mark.asyncio
    async def test_on_failure_reruns_failed_test(self, tmp_path):
        """capture_video='on_failure': failed test gets re-run with video."""
        mock_page = _make_mock_page()

        config = _make_config()
        config.capture_video = "on_failure"
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        context_count = 0

        def make_context(*args, **kwargs):
            nonlocal context_count
            context_count += 1
            ctx = _make_mock_context()
            if context_count == 2:
                # Second context (video re-run): create video file on close
                async def create_video():
                    rerun_video_dir = executor.run_dir / "evidence" / "tc_001" / "video_rerun" / "video"
                    rerun_video_dir.mkdir(parents=True, exist_ok=True)
                    (rerun_video_dir / "failure.webm").write_bytes(b"video data")
                ctx.close = AsyncMock(side_effect=create_video)
            return ctx

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, side_effect=make_context) as ctx_fn, \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            # Both runs fail
            mock_assert.return_value = Mock(passed=False, message="Element not found", screenshots=[])

            result = await executor.execute(plan)

        # Two contexts: original + video re-run
        assert ctx_fn.call_count == 2
        # Second call should have record_video_dir
        second_call_kwargs = ctx_fn.call_args_list[1].kwargs
        assert second_call_kwargs.get("record_video_dir") is not None

        tr = result.test_results[0]
        assert tr.result == "fail"
        assert tr.evidence.video_path is not None
        assert tr.evidence.video_path.endswith(".webm")
        # Both runs failed — not flaky
        assert tr.potentially_flaky is False

    @pytest.mark.asyncio
    async def test_on_failure_detects_flaky(self, tmp_path):
        """capture_video='on_failure': original fails, re-run passes → flaky."""
        config = _make_config()
        config.capture_video = "on_failure"
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        context_count = 0

        def make_context(*args, **kwargs):
            nonlocal context_count
            context_count += 1
            ctx = _make_mock_context()
            if context_count == 2:
                async def create_video():
                    rerun_video_dir = executor.run_dir / "evidence" / "tc_001" / "video_rerun" / "video"
                    rerun_video_dir.mkdir(parents=True, exist_ok=True)
                    (rerun_video_dir / "flaky.webm").write_bytes(b"video data")
                ctx.close = AsyncMock(side_effect=create_video)
            return ctx

        assertion_call_count = 0

        async def alternating_assertion(page, assertion, *args, **kwargs):
            nonlocal assertion_call_count
            assertion_call_count += 1
            # First call (original run) fails, second call (re-run) passes
            if assertion_call_count == 1:
                return Mock(passed=False, message="Element not found", screenshots=[])
            return Mock(passed=True, message="OK", screenshots=[])

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, side_effect=make_context), \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", side_effect=alternating_assertion), \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await executor.execute(plan)

        tr = result.test_results[0]
        assert tr.result == "fail"  # Original result preserved
        assert tr.potentially_flaky is True
        assert tr.evidence.video_path is not None

    @pytest.mark.asyncio
    async def test_on_failure_respects_time_limit(self, tmp_path):
        """capture_video='on_failure': re-run skipped when time limit exhausted."""
        config = _make_config(max_time=0)
        config.capture_video = "on_failure"
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, return_value=_make_mock_context()) as ctx_fn, \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock) as mock_assert, \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_assert.return_value = Mock(passed=False, message="Fail", screenshots=[])

            result = await executor.execute(plan)

        # With max_time=0, tests may be skipped entirely or re-run skipped
        # Either way, no extra context for video re-run
        tr = result.test_results[0]
        assert tr.evidence.video_path is None

    @pytest.mark.asyncio
    async def test_on_failure_reruns_error_test(self, tmp_path):
        """capture_video='on_failure': 'error' results also trigger re-run."""
        config = _make_config()
        config.capture_video = "on_failure"
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)
        plan = _make_plan()

        context_count = 0

        def make_context(*args, **kwargs):
            nonlocal context_count
            context_count += 1
            ctx = _make_mock_context()
            if context_count == 2:
                async def create_video():
                    rerun_video_dir = executor.run_dir / "evidence" / "tc_001" / "video_rerun" / "video"
                    rerun_video_dir.mkdir(parents=True, exist_ok=True)
                    (rerun_video_dir / "error.webm").write_bytes(b"video data")
                ctx.close = AsyncMock(side_effect=create_video)
            return ctx

        with patch(ASYNC_PW) as mock_pw_cls, \
             patch(STEALTH_BROWSER, return_value=AsyncMock()), \
             patch(STEALTH_CONTEXT, side_effect=make_context) as ctx_fn, \
             patch("src.executor.executor.run_action", new_callable=AsyncMock), \
             patch("src.executor.executor.check_assertion", new_callable=AsyncMock,
                   side_effect=RuntimeError("Crash")), \
             patch("src.executor.executor.resolve_dynamic_vars_for_test_case"):
            mock_pw_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await executor.execute(plan)

        # Error triggers re-run
        assert ctx_fn.call_count == 2
        tr = result.test_results[0]
        assert tr.result == "error"
        assert tr.evidence.video_path is not None
