"""Tests for API test execution — _run_api_action and Executor._run_api_test."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.executor.executor import Executor, _run_api_action
from src.models.config import CrawlConfig, FrameworkConfig, ViewportConfig
from src.models.test_plan import Action, Assertion, TestCase, TestPlan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config():
    return FrameworkConfig(
        target_url="http://localhost:8000",
        categories=["api"],
        crawl=CrawlConfig(
            target_url="http://localhost:8000",
            viewport=ViewportConfig(width=1280, height=720, name="desktop"),
        ),
        max_tests_per_run=50,
        max_execution_time_seconds=1800,
        selector_timeout_seconds=5,
        ai_model="claude-opus-4-6",
        ai_max_fallback_calls_per_test=3,
        ai_max_planning_tokens=32000,
        visual_diff_tolerance=0.05,
        report_output_dir="./test-reports",
    )


def _make_api_test_case(
    test_id="tc_api_001",
    steps=None,
    assertions=None,
    preconditions=None,
) -> TestCase:
    return TestCase(
        test_id=test_id,
        name="[GET] List items",
        category="api",
        priority=2,
        target_page_id="",
        requires_auth=False,
        coverage_signature=f"sig_{test_id}",
        steps=steps or [Action(
            action_type="api_get",
            selector="http://localhost:8000/api/items",
            description="GET /api/items",
        )],
        assertions=assertions or [Assertion(
            assertion_type="response_status",
            expected_value="200",
            description="Status is 200",
        )],
        preconditions=preconditions or [],
        timeout_seconds=30,
    )


def _make_mock_api_response(status=200, body='{"items":[]}', headers=None, json_data=None):
    """Return an AsyncMock mimicking Playwright's APIResponse."""
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers or {"content-type": "application/json"}
    resp.text = AsyncMock(return_value=body)
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {"items": []})
    return resp


# ---------------------------------------------------------------------------
# _run_api_action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRunApiAction:

    async def test_get_calls_api_get(self):
        api = AsyncMock()
        api.get = AsyncMock(return_value=_make_mock_api_response())
        action = Action(action_type="api_get", selector="http://localhost/api/users")

        result = await _run_api_action(api, action)

        api.get.assert_awaited_once_with("http://localhost/api/users")
        assert result["status"] == 200
        assert result["url"] == "http://localhost/api/users"

    async def test_post_with_json_body(self):
        api = AsyncMock()
        api.post = AsyncMock(return_value=_make_mock_api_response(status=201))
        action = Action(
            action_type="api_post",
            selector="http://localhost/api/users",
            value='{"name": "alice"}',
        )

        result = await _run_api_action(api, action)

        api.post.assert_awaited_once_with(
            "http://localhost/api/users",
            json={"name": "alice"},
        )
        assert result["status"] == 201

    async def test_post_with_raw_string_body(self):
        """Unparseable JSON value is sent as raw data string."""
        api = AsyncMock()
        api.post = AsyncMock(return_value=_make_mock_api_response(status=200))
        action = Action(
            action_type="api_post",
            selector="http://localhost/api/raw",
            value="not-json",
        )

        result = await _run_api_action(api, action)

        api.post.assert_awaited_once_with(
            "http://localhost/api/raw",
            data="not-json",
        )

    async def test_put_with_json_body(self):
        api = AsyncMock()
        api.put = AsyncMock(return_value=_make_mock_api_response())
        action = Action(
            action_type="api_put",
            selector="http://localhost/api/users/1",
            value='{"name": "bob"}',
        )

        await _run_api_action(api, action)

        api.put.assert_awaited_once_with(
            "http://localhost/api/users/1",
            json={"name": "bob"},
        )

    async def test_delete_no_body(self):
        api = AsyncMock()
        api.delete = AsyncMock(return_value=_make_mock_api_response(status=204, body=""))
        action = Action(
            action_type="api_delete",
            selector="http://localhost/api/users/1",
        )

        result = await _run_api_action(api, action)

        api.delete.assert_awaited_once_with("http://localhost/api/users/1")
        assert result["status"] == 204

    async def test_patch_with_json_body(self):
        api = AsyncMock()
        api.patch = AsyncMock(return_value=_make_mock_api_response())
        action = Action(
            action_type="api_patch",
            selector="http://localhost/api/users/1",
            value='{"active": true}',
        )

        await _run_api_action(api, action)

        api.patch.assert_awaited_once_with(
            "http://localhost/api/users/1",
            json={"active": True},
        )

    async def test_missing_url_raises(self):
        api = AsyncMock()
        action = Action(action_type="api_get", selector=None)

        with pytest.raises(ValueError, match="requires a URL"):
            await _run_api_action(api, action)

    async def test_unknown_action_type_raises(self):
        api = AsyncMock()
        action = Action(action_type="api_head", selector="http://localhost/api")

        with pytest.raises(ValueError, match="Unknown API action type"):
            await _run_api_action(api, action)

    async def test_returns_parsed_json(self):
        api = AsyncMock()
        json_data = {"id": 1, "name": "alice"}
        api.get = AsyncMock(return_value=_make_mock_api_response(
            body='{"id":1,"name":"alice"}', json_data=json_data
        ))
        action = Action(action_type="api_get", selector="http://localhost/api/users/1")

        result = await _run_api_action(api, action)

        assert result["json"] == json_data
        assert result["body"] == '{"id":1,"name":"alice"}'

    async def test_non_json_response_json_is_none(self):
        """If response.json() raises, result['json'] is None."""
        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"content-type": "text/plain"}
        resp.text = AsyncMock(return_value="plain text")
        resp.json = AsyncMock(side_effect=Exception("not json"))

        api = AsyncMock()
        api.get = AsyncMock(return_value=resp)
        action = Action(action_type="api_get", selector="http://localhost/api/plain")

        result = await _run_api_action(api, action)

        assert result["json"] is None
        assert result["body"] == "plain text"

    async def test_no_body_post_sends_no_kwargs(self):
        """POST with no value sends no body kwargs."""
        api = AsyncMock()
        api.post = AsyncMock(return_value=_make_mock_api_response(status=201))
        action = Action(action_type="api_post", selector="http://localhost/api/ping")

        await _run_api_action(api, action)

        api.post.assert_awaited_once_with("http://localhost/api/ping")


# ---------------------------------------------------------------------------
# Executor._run_api_test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRunApiTest:

    async def test_passing_test_returns_pass(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_resp = _make_mock_api_response(status=200)
        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=mock_resp)

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case(
            assertions=[Assertion(
                assertion_type="response_status",
                expected_value="200",
            )]
        )

        result = await executor._run_api_test(context, tc)

        assert result.result == "pass"
        assert result.assertions_passed == 1
        assert result.assertions_failed == 0

    async def test_failing_assertion_returns_fail(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_resp = _make_mock_api_response(status=404)
        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=mock_resp)

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case(
            assertions=[Assertion(
                assertion_type="response_status",
                expected_value="200",
            )]
        )

        result = await executor._run_api_test(context, tc)

        assert result.result == "fail"
        assert result.assertions_failed == 1
        assert result.failure_reason is not None

    async def test_step_error_aborts_remaining_steps(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_api = AsyncMock()
        mock_api.get = AsyncMock(side_effect=Exception("Connection refused"))

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case(
            steps=[
                Action(action_type="api_get", selector="http://localhost/api/one"),
                Action(action_type="api_get", selector="http://localhost/api/two"),
            ],
            assertions=[Assertion(assertion_type="response_status", expected_value="200")],
        )

        result = await executor._run_api_test(context, tc)

        # When a step aborts and assertions run against empty response (fail),
        # result is "fail". "error" only when aborted with zero assertion failures.
        assert result.result in ("fail", "error")
        skipped = [s for s in result.step_results if s.status == "skip"]
        assert len(skipped) == 1  # second step was skipped

    async def test_no_page_is_opened(self, tmp_path):
        """API tests must not open a browser page."""
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=_make_mock_api_response())

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case()
        await executor._run_api_test(context, tc)

        context.new_page.assert_not_called()

    async def test_uses_context_request(self, tmp_path):
        """Executor uses context.request, not a separate API context."""
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=_make_mock_api_response())

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case()
        await executor._run_api_test(context, tc)

        mock_api.get.assert_awaited_once()

    async def test_precondition_actions_are_executed(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=_make_mock_api_response())

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case(
            preconditions=[Action(
                action_type="api_get",
                selector="http://localhost/api/setup",
            )],
            steps=[Action(
                action_type="api_get",
                selector="http://localhost/api/items",
            )],
        )

        result = await executor._run_api_test(context, tc)

        assert mock_api.get.await_count == 2
        assert result.result == "pass"

    async def test_multiple_assertions_all_pass(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        json_data = {"items": [{"id": 1}], "total": 1}
        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=_make_mock_api_response(
            status=200,
            body='{"items":[{"id":1}],"total":1}',
            json_data=json_data,
        ))

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case(
            assertions=[
                Assertion(assertion_type="response_status", expected_value="200"),
                Assertion(assertion_type="response_json_path", selector="total", expected_value="1"),
                Assertion(assertion_type="response_body_contains", expected_value="items"),
            ],
        )

        result = await executor._run_api_test(context, tc)

        assert result.result == "pass"
        assert result.assertions_passed == 3
        assert result.assertions_failed == 0

    async def test_result_contains_response_url(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=_make_mock_api_response())

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case(
            steps=[Action(
                action_type="api_get",
                selector="http://localhost:8000/api/items",
            )]
        )

        result = await executor._run_api_test(context, tc)
        assert result.actual_url == "http://localhost:8000/api/items"

    async def test_category_is_preserved_in_result(self, tmp_path):
        config = _make_config()
        executor = Executor(config, ai_client=None, runs_dir=tmp_path)

        mock_api = AsyncMock()
        mock_api.get = AsyncMock(return_value=_make_mock_api_response())

        context = AsyncMock()
        context.request = mock_api

        tc = _make_api_test_case()
        result = await executor._run_api_test(context, tc)

        assert result.category == "api"
