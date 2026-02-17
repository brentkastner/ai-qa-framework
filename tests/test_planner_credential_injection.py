"""Tests for post-plan credential injection."""

import pytest

from src.models.config import AuthConfig, FrameworkConfig
from src.models.test_plan import Action, Assertion, TestCase, TestPlan
from src.planner.planner import (
    AUTH_PLACEHOLDER_LOGIN_URL,
    AUTH_PLACEHOLDER_PASSWORD,
    AUTH_PLACEHOLDER_USERNAME,
    Planner,
)


@pytest.fixture
def auth_config():
    return AuthConfig(
        login_url="https://example.com/login",
        username="testuser@example.com",
        password="S3cretP@ss!",
    )


@pytest.fixture
def config_with_auth(auth_config):
    return FrameworkConfig(
        target_url="https://example.com",
        auth=auth_config,
    )


@pytest.fixture
def config_no_auth():
    return FrameworkConfig(target_url="https://example.com")


def _make_plan(steps, preconditions=None, assertions=None):
    """Helper to build a TestPlan with given actions."""
    tc = TestCase(
        test_id="tc_001",
        name="Test",
        preconditions=preconditions or [],
        steps=steps,
        assertions=assertions or [],
    )
    return TestPlan(
        plan_id="plan_001",
        generated_at="2025-01-01T00:00:00Z",
        target_url="https://example.com",
        test_cases=[tc],
    )


class TestInjectCredentials:
    """Tests for Planner._inject_credentials()."""

    def test_username_placeholder_replaced(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan([
            Action(action_type="fill", selector="#email",
                   value=AUTH_PLACEHOLDER_USERNAME),
        ])
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value == "testuser@example.com"

    def test_password_placeholder_replaced(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan([
            Action(action_type="fill", selector="#password",
                   value=AUTH_PLACEHOLDER_PASSWORD),
        ])
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value == "S3cretP@ss!"

    def test_login_url_placeholder_replaced(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan([
            Action(action_type="navigate",
                   value=AUTH_PLACEHOLDER_LOGIN_URL),
        ])
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value == "https://example.com/login"

    def test_no_auth_config_strips_auth_test_cases(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        plan = _make_plan([
            Action(action_type="fill", selector="#email",
                   value=AUTH_PLACEHOLDER_USERNAME),
        ])
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_no_placeholders_is_noop(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan([
            Action(action_type="fill", selector="#name", value="John Doe"),
        ])
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value == "John Doe"

    def test_preconditions_are_processed(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan(
            steps=[Action(action_type="click", selector="#submit")],
            preconditions=[
                Action(action_type="navigate",
                       value=AUTH_PLACEHOLDER_LOGIN_URL),
                Action(action_type="fill", selector="#email",
                       value=AUTH_PLACEHOLDER_USERNAME),
            ],
        )
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].preconditions[0].value == "https://example.com/login"
        assert result.test_cases[0].preconditions[1].value == "testuser@example.com"

    def test_assertion_expected_value_replaced(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan(
            steps=[Action(action_type="click", selector="#submit")],
            assertions=[
                Assertion(
                    assertion_type="url_matches",
                    expected_value=AUTH_PLACEHOLDER_LOGIN_URL,
                ),
            ],
        )
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].assertions[0].expected_value == "https://example.com/login"

    def test_none_values_are_skipped(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan([
            Action(action_type="click", selector="#btn", value=None),
        ])
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value is None

    def test_multiple_placeholders_in_one_value(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        plan = _make_plan([
            Action(action_type="fill", selector="#combined",
                   value=f"{AUTH_PLACEHOLDER_USERNAME}:{AUTH_PLACEHOLDER_PASSWORD}"),
        ])
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value == "testuser@example.com:S3cretP@ss!"
