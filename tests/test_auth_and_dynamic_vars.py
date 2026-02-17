"""Tests for auth-aware planning, credential injection, and dynamic variable resolution.

Covers:
- Auth placeholder stripping when auth is not configured
- Auth placeholder replacement when auth IS configured
- Planning prompt auth-awareness (has_auth true/false)
- Dynamic variable resolution ({{$timestamp}})
- Regex correctness (double-brace matching)
- Per-test-case timestamp consistency
"""

import re
import time

import pytest

from src.ai.prompts.planning import PLANNING_SYSTEM_PROMPT, build_planning_prompt
from src.executor.action_runner import (
    _DYNAMIC_VAR_RE,
    _build_dynamic_vars,
    _resolve_dynamic_vars,
    resolve_dynamic_vars_for_test_case,
)
from src.models.config import AuthConfig, FrameworkConfig
from src.models.test_plan import Action, Assertion, TestCase, TestPlan
from src.planner.planner import (
    AUTH_PLACEHOLDER_LOGIN_URL,
    AUTH_PLACEHOLDER_PASSWORD,
    AUTH_PLACEHOLDER_USERNAME,
    Planner,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_test_case(
    test_id="tc_001",
    preconditions=None,
    steps=None,
    assertions=None,
):
    return TestCase(
        test_id=test_id,
        name=f"Test {test_id}",
        preconditions=preconditions or [],
        steps=steps or [],
        assertions=assertions or [],
    )


def _make_plan(*test_cases):
    return TestPlan(
        plan_id="plan_001",
        generated_at="2025-01-01T00:00:00Z",
        target_url="https://example.com",
        test_cases=list(test_cases),
    )


@pytest.fixture
def config_with_auth():
    return FrameworkConfig(
        target_url="https://example.com",
        auth=AuthConfig(
            login_url="https://example.com/login",
            username="testuser@example.com",
            password="S3cretP@ss!",
        ),
    )


@pytest.fixture
def config_no_auth():
    return FrameworkConfig(target_url="https://example.com")


# ============================================================================
# Auth Placeholder Stripping (auth=None)
# ============================================================================


class TestAuthPlaceholderStripping:
    """When auth is not configured, test cases with unresolved auth placeholders
    must be removed from the plan."""

    def test_removes_tc_with_auth_login_url_in_steps(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="navigate", value=AUTH_PLACEHOLDER_LOGIN_URL),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_removes_tc_with_auth_username_in_steps(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#email",
                   value=AUTH_PLACEHOLDER_USERNAME),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_removes_tc_with_auth_password_in_steps(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#pass",
                   value=AUTH_PLACEHOLDER_PASSWORD),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_removes_tc_with_auth_placeholder_in_preconditions(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(
            preconditions=[
                Action(action_type="navigate", value=AUTH_PLACEHOLDER_LOGIN_URL),
                Action(action_type="fill", selector="#email",
                       value=AUTH_PLACEHOLDER_USERNAME),
            ],
            steps=[Action(action_type="click", selector="#submit")],
        )
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_removes_tc_with_auth_placeholder_in_assertions(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(
            steps=[Action(action_type="click", selector="#submit")],
            assertions=[
                Assertion(assertion_type="url_matches",
                          expected_value=AUTH_PLACEHOLDER_LOGIN_URL),
            ],
        )
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_keeps_tc_without_auth_placeholders(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="navigate", value="https://example.com/public"),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 1

    def test_mixed_plan_only_removes_auth_cases(self, config_no_auth):
        """A plan with both auth and non-auth test cases: only auth ones removed."""
        planner = Planner(config_no_auth, ai_client=None)
        tc_auth = _make_test_case(
            test_id="tc_auth",
            steps=[
                Action(action_type="navigate", value=AUTH_PLACEHOLDER_LOGIN_URL),
                Action(action_type="fill", selector="#email",
                       value=AUTH_PLACEHOLDER_USERNAME),
            ],
        )
        tc_public = _make_test_case(
            test_id="tc_public",
            steps=[
                Action(action_type="navigate", value="https://example.com/about"),
            ],
        )
        tc_form = _make_test_case(
            test_id="tc_form",
            steps=[
                Action(action_type="fill", selector="#search", value="hello"),
                Action(action_type="click", selector="#go"),
            ],
        )
        plan = _make_plan(tc_auth, tc_public, tc_form)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 2
        ids = [tc.test_id for tc in result.test_cases]
        assert "tc_auth" not in ids
        assert "tc_public" in ids
        assert "tc_form" in ids

    def test_embedded_placeholder_in_value_detected(self, config_no_auth):
        """A placeholder embedded inside a larger string is still detected."""
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#field",
                   value=f"prefix-{AUTH_PLACEHOLDER_USERNAME}-suffix"),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_empty_plan_unchanged(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        plan = _make_plan()
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0

    def test_none_values_do_not_trigger_removal(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="click", selector="#btn", value=None),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 1


# ============================================================================
# Auth Placeholder Replacement (auth configured)
# ============================================================================


class TestAuthPlaceholderReplacement:
    """When auth IS configured, placeholders are replaced with real values."""

    def test_all_three_placeholders_replaced(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        tc = _make_test_case(
            preconditions=[
                Action(action_type="navigate", value=AUTH_PLACEHOLDER_LOGIN_URL),
            ],
            steps=[
                Action(action_type="fill", selector="#email",
                       value=AUTH_PLACEHOLDER_USERNAME),
                Action(action_type="fill", selector="#pass",
                       value=AUTH_PLACEHOLDER_PASSWORD),
                Action(action_type="click", selector="#submit"),
            ],
        )
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].preconditions[0].value == "https://example.com/login"
        assert result.test_cases[0].steps[0].value == "testuser@example.com"
        assert result.test_cases[0].steps[1].value == "S3cretP@ss!"
        # Non-placeholder step unchanged
        assert result.test_cases[0].steps[2].value is None

    def test_assertion_placeholders_replaced(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        tc = _make_test_case(
            steps=[Action(action_type="click", selector="#x")],
            assertions=[
                Assertion(assertion_type="url_matches",
                          expected_value=AUTH_PLACEHOLDER_LOGIN_URL),
            ],
        )
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].assertions[0].expected_value == "https://example.com/login"

    def test_no_placeholder_actions_unchanged(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#name", value="John Doe"),
            Action(action_type="navigate", value="https://example.com/public"),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value == "John Doe"
        assert result.test_cases[0].steps[1].value == "https://example.com/public"

    def test_multiple_test_cases_all_injected(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        tc1 = _make_test_case(
            test_id="tc_1",
            steps=[Action(action_type="fill", selector="#email",
                          value=AUTH_PLACEHOLDER_USERNAME)],
        )
        tc2 = _make_test_case(
            test_id="tc_2",
            steps=[Action(action_type="fill", selector="#pass",
                          value=AUTH_PLACEHOLDER_PASSWORD)],
        )
        plan = _make_plan(tc1, tc2)
        result = planner._inject_credentials(plan)
        assert result.test_cases[0].steps[0].value == "testuser@example.com"
        assert result.test_cases[1].steps[0].value == "S3cretP@ss!"


# ============================================================================
# has_auth_placeholders static method
# ============================================================================


class TestHasAuthPlaceholders:
    """Tests for Planner._has_auth_placeholders()."""

    def test_detects_auth_login_url(self):
        tc = _make_test_case(steps=[
            Action(action_type="navigate", value=AUTH_PLACEHOLDER_LOGIN_URL),
        ])
        assert Planner._has_auth_placeholders(tc) is True

    def test_detects_auth_username(self):
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#e", value=AUTH_PLACEHOLDER_USERNAME),
        ])
        assert Planner._has_auth_placeholders(tc) is True

    def test_detects_auth_password(self):
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#p", value=AUTH_PLACEHOLDER_PASSWORD),
        ])
        assert Planner._has_auth_placeholders(tc) is True

    def test_detects_in_preconditions(self):
        tc = _make_test_case(
            preconditions=[
                Action(action_type="navigate", value=AUTH_PLACEHOLDER_LOGIN_URL),
            ],
        )
        assert Planner._has_auth_placeholders(tc) is True

    def test_detects_in_assertions(self):
        tc = _make_test_case(
            assertions=[
                Assertion(assertion_type="url_matches",
                          expected_value=AUTH_PLACEHOLDER_LOGIN_URL),
            ],
        )
        assert Planner._has_auth_placeholders(tc) is True

    def test_false_for_no_placeholders(self):
        tc = _make_test_case(steps=[
            Action(action_type="navigate", value="https://example.com"),
            Action(action_type="fill", selector="#q", value="search term"),
        ])
        assert Planner._has_auth_placeholders(tc) is False

    def test_false_for_none_values(self):
        tc = _make_test_case(steps=[
            Action(action_type="click", selector="#btn", value=None),
        ])
        assert Planner._has_auth_placeholders(tc) is False

    def test_false_for_empty_test_case(self):
        tc = _make_test_case()
        assert Planner._has_auth_placeholders(tc) is False

    def test_detects_embedded_placeholder(self):
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#f",
                   value=f"user:{AUTH_PLACEHOLDER_PASSWORD}"),
        ])
        assert Planner._has_auth_placeholders(tc) is True

    def test_dynamic_var_not_confused_with_auth_placeholder(self):
        """{{$timestamp}} should NOT be detected as an auth placeholder."""
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#id",
                   value="vault-{{$timestamp}}"),
        ])
        assert Planner._has_auth_placeholders(tc) is False


# ============================================================================
# Planning Prompt — Auth Awareness
# ============================================================================


class TestPlanningPromptAuth:
    """Tests that the planning prompt correctly handles auth/no-auth guidance."""

    def test_prompt_contains_auth_placeholder_tokens(self):
        """The planning prompt must document all three placeholder tokens."""
        assert "{{auth_login_url}}" in PLANNING_SYSTEM_PROMPT
        assert "{{auth_username}}" in PLANNING_SYSTEM_PROMPT
        assert "{{auth_password}}" in PLANNING_SYSTEM_PROMPT

    def test_prompt_has_auth_true_section(self):
        """Prompt must instruct AI on behavior when has_auth is true."""
        assert '"has_auth": true' in PLANNING_SYSTEM_PROMPT

    def test_prompt_has_auth_false_section(self):
        """Prompt must instruct AI on behavior when has_auth is false."""
        assert '"has_auth": false' in PLANNING_SYSTEM_PROMPT

    def test_prompt_forbids_placeholders_when_no_auth(self):
        """When has_auth is false, prompt should say NOT to use placeholders."""
        # Find the has_auth: false section and verify it says not to use placeholders
        idx_false = PLANNING_SYSTEM_PROMPT.index('"has_auth": false')
        section_after_false = PLANNING_SYSTEM_PROMPT[idx_false:idx_false + 500]
        assert "Do NOT" in section_after_false
        assert "{{auth_login_url}}" in section_after_false

    def test_prompt_mentions_dynamic_timestamp_variable(self):
        """Prompt should mention {{$timestamp}} for unique test data."""
        assert "{{$timestamp}}" in PLANNING_SYSTEM_PROMPT

    def test_prompt_explains_timestamp_replacement(self):
        """Prompt should explain that {{$timestamp}} is replaced at runtime."""
        assert "runtime" in PLANNING_SYSTEM_PROMPT.lower()
        assert "unique" in PLANNING_SYSTEM_PROMPT.lower()


# ============================================================================
# Planning Prompt — Site Model has_auth Field
# ============================================================================


class TestSiteModelAuthSummary:
    """Tests that the site model summary correctly passes has_auth."""

    def _make_site_model(self, has_auth_flow):
        from src.models.site_model import AuthFlow, SiteModel
        auth_flow = None
        if has_auth_flow:
            auth_flow = AuthFlow(
                login_url="https://example.com/login",
                detection_method="explicit",
            )
        return SiteModel(
            base_url="https://example.com",
            pages=[],
            auth_flow=auth_flow,
        )

    def test_summarize_includes_has_auth_true(self, config_with_auth):
        planner = Planner(config_with_auth, ai_client=None)
        site_model = self._make_site_model(has_auth_flow=True)
        summary = planner._summarize_site_model(site_model)
        assert '"has_auth": true' in summary

    def test_summarize_includes_has_auth_false(self, config_no_auth):
        planner = Planner(config_no_auth, ai_client=None)
        site_model = self._make_site_model(has_auth_flow=False)
        summary = planner._summarize_site_model(site_model)
        assert '"has_auth": false' in summary


# ============================================================================
# Dynamic Variable Regex
# ============================================================================


class TestDynamicVarRegex:
    """Tests for the _DYNAMIC_VAR_RE regex pattern."""

    def test_matches_timestamp(self):
        assert _DYNAMIC_VAR_RE.search("{{$timestamp}}")

    def test_captures_variable_name(self):
        m = _DYNAMIC_VAR_RE.search("prefix-{{$timestamp}}-suffix")
        assert m is not None
        assert m.group(1) == "timestamp"

    def test_full_match_includes_both_braces(self):
        m = _DYNAMIC_VAR_RE.search("{{$timestamp}}")
        assert m is not None
        assert m.group(0) == "{{$timestamp}}"

    def test_does_not_match_auth_placeholders(self):
        """Auth placeholders like {{auth_login_url}} have no $ prefix."""
        assert _DYNAMIC_VAR_RE.search("{{auth_login_url}}") is None
        assert _DYNAMIC_VAR_RE.search("{{auth_username}}") is None
        assert _DYNAMIC_VAR_RE.search("{{auth_password}}") is None

    def test_does_not_match_single_braces(self):
        assert _DYNAMIC_VAR_RE.search("{$timestamp}") is None

    def test_does_not_match_missing_dollar(self):
        assert _DYNAMIC_VAR_RE.search("{{timestamp}}") is None

    def test_matches_other_variable_names(self):
        m = _DYNAMIC_VAR_RE.search("{{$randomInt}}")
        assert m is not None
        assert m.group(1) == "randomInt"

    def test_matches_multiple_in_string(self):
        matches = _DYNAMIC_VAR_RE.findall("{{$timestamp}}-{{$randomInt}}")
        assert matches == ["timestamp", "randomInt"]


# ============================================================================
# Dynamic Variable Resolution — Single Value
# ============================================================================


class TestResolveDynamicVars:
    """Tests for _resolve_dynamic_vars function."""

    def test_timestamp_replaced(self):
        resolved = {"timestamp": "1234567890"}
        result = _resolve_dynamic_vars("vault-{{$timestamp}}", resolved)
        assert result == "vault-1234567890"

    def test_no_trailing_brace(self):
        """Regression: previously the regex only matched one closing brace,
        leaving a stray } in the output."""
        resolved = {"timestamp": "1234567890"}
        result = _resolve_dynamic_vars("id-{{$timestamp}}", resolved)
        assert "}" not in result
        assert result == "id-1234567890"

    def test_multiple_vars_in_one_string(self):
        resolved = {"timestamp": "123", "randomInt": "42"}
        result = _resolve_dynamic_vars("{{$timestamp}}-{{$randomInt}}", resolved)
        assert result == "123-42"

    def test_unknown_variable_left_as_is(self):
        resolved = {"timestamp": "123"}
        result = _resolve_dynamic_vars("{{$unknownVar}}", resolved)
        assert result == "{{$unknownVar}}"

    def test_no_dynamic_vars_unchanged(self):
        resolved = {"timestamp": "123"}
        result = _resolve_dynamic_vars("plain text", resolved)
        assert result == "plain text"

    def test_empty_string_unchanged(self):
        resolved = {"timestamp": "123"}
        result = _resolve_dynamic_vars("", resolved)
        assert result == ""

    def test_auth_placeholder_not_resolved(self):
        """Auth placeholders like {{auth_username}} should NOT be touched."""
        resolved = {"timestamp": "123"}
        result = _resolve_dynamic_vars("{{auth_username}}", resolved)
        assert result == "{{auth_username}}"


# ============================================================================
# Dynamic Variable Resolution — Build Snapshot
# ============================================================================


class TestBuildDynamicVars:
    """Tests for _build_dynamic_vars snapshot function."""

    def test_returns_timestamp(self):
        result = _build_dynamic_vars()
        assert "timestamp" in result
        assert result["timestamp"].isdigit()

    def test_timestamp_is_recent(self):
        result = _build_dynamic_vars()
        ts = int(result["timestamp"])
        now = int(time.time())
        # Should be within 2 seconds
        assert abs(ts - now) < 2


# ============================================================================
# Per-Test-Case Dynamic Variable Resolution
# ============================================================================


class TestResolveForTestCase:
    """Tests for resolve_dynamic_vars_for_test_case."""

    def test_same_timestamp_across_all_actions(self):
        """All actions in a test case should share the same timestamp value."""
        actions = [
            Action(action_type="fill", selector="#id",
                   value="vault-{{$timestamp}}"),
            Action(action_type="fill", selector="#name",
                   value="name-{{$timestamp}}"),
            Action(action_type="fill", selector="#ref",
                   value="ref-{{$timestamp}}"),
        ]
        resolve_dynamic_vars_for_test_case(actions)

        # Extract the resolved timestamps
        ts1 = actions[0].value.replace("vault-", "")
        ts2 = actions[1].value.replace("name-", "")
        ts3 = actions[2].value.replace("ref-", "")
        assert ts1 == ts2 == ts3
        assert ts1.isdigit()

    def test_preconditions_and_steps_share_timestamp(self):
        """Simulates the real use case: precondition creates a vault,
        step logs in with the same vault ID."""
        preconditions = [
            Action(action_type="fill", selector="#vaultId",
                   value="logintest-{{$timestamp}}"),
            Action(action_type="fill", selector="#password",
                   value="SecurePass123!"),
        ]
        steps = [
            Action(action_type="fill", selector="#vault-id-input",
                   value="logintest-{{$timestamp}}"),
            Action(action_type="fill", selector="#password-input",
                   value="SecurePass123!"),
        ]
        resolve_dynamic_vars_for_test_case(preconditions + steps)

        # The vault IDs must match
        assert preconditions[0].value == steps[0].value
        assert "{{$timestamp}}" not in preconditions[0].value
        # Non-dynamic values untouched
        assert preconditions[1].value == "SecurePass123!"
        assert steps[1].value == "SecurePass123!"

    def test_actions_without_vars_untouched(self):
        actions = [
            Action(action_type="navigate", value="https://example.com"),
            Action(action_type="click", selector="#btn", value=None),
            Action(action_type="wait", value="2000"),
        ]
        resolve_dynamic_vars_for_test_case(actions)
        assert actions[0].value == "https://example.com"
        assert actions[1].value is None
        assert actions[2].value == "2000"

    def test_empty_action_list(self):
        """Should handle empty list without error."""
        resolve_dynamic_vars_for_test_case([])

    def test_no_trailing_brace_after_resolution(self):
        """Regression test: ensure no stray } in resolved values."""
        actions = [
            Action(action_type="fill", selector="#id",
                   value="test-{{$timestamp}}"),
        ]
        resolve_dynamic_vars_for_test_case(actions)
        assert not actions[0].value.endswith("}")
        assert "}" not in actions[0].value.split("-")[1]

    def test_different_test_cases_get_different_timestamps(self):
        """Each call to resolve_dynamic_vars_for_test_case generates a fresh
        snapshot, so different test cases can (and likely will) have different
        timestamps if time has elapsed."""
        actions1 = [
            Action(action_type="fill", selector="#id",
                   value="a-{{$timestamp}}"),
        ]
        actions2 = [
            Action(action_type="fill", selector="#id",
                   value="b-{{$timestamp}}"),
        ]
        resolve_dynamic_vars_for_test_case(actions1)
        resolve_dynamic_vars_for_test_case(actions2)
        # Both should be resolved (not contain placeholder)
        assert "{{$timestamp}}" not in actions1[0].value
        assert "{{$timestamp}}" not in actions2[0].value


# ============================================================================
# Integration: Credential Injection + Dynamic Vars Don't Interfere
# ============================================================================


class TestAuthAndDynamicVarsSeparation:
    """Ensure auth placeholders and dynamic variables don't interfere."""

    def test_dynamic_var_in_plan_preserved_through_injection(self, config_with_auth):
        """Dynamic variables should pass through credential injection untouched."""
        planner = Planner(config_with_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#id",
                   value="vault-{{$timestamp}}"),
            Action(action_type="fill", selector="#email",
                   value=AUTH_PLACEHOLDER_USERNAME),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        # Auth replaced, dynamic var untouched (resolved later at runtime)
        assert result.test_cases[0].steps[0].value == "vault-{{$timestamp}}"
        assert result.test_cases[0].steps[1].value == "testuser@example.com"

    def test_no_auth_strips_auth_but_keeps_dynamic_var_cases(self, config_no_auth):
        """Without auth config: test cases with only dynamic vars are kept,
        test cases with auth placeholders are removed."""
        planner = Planner(config_no_auth, ai_client=None)
        tc_dynamic = _make_test_case(
            test_id="tc_dynamic",
            steps=[
                Action(action_type="fill", selector="#id",
                       value="vault-{{$timestamp}}"),
            ],
        )
        tc_auth = _make_test_case(
            test_id="tc_auth",
            steps=[
                Action(action_type="navigate", value=AUTH_PLACEHOLDER_LOGIN_URL),
            ],
        )
        plan = _make_plan(tc_dynamic, tc_auth)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 1
        assert result.test_cases[0].test_id == "tc_dynamic"

    def test_tc_with_both_auth_and_dynamic_vars_removed_when_no_auth(self, config_no_auth):
        """A test case that has both auth placeholders AND dynamic vars
        should still be removed when auth is not configured."""
        planner = Planner(config_no_auth, ai_client=None)
        tc = _make_test_case(steps=[
            Action(action_type="fill", selector="#id",
                   value="vault-{{$timestamp}}"),
            Action(action_type="fill", selector="#email",
                   value=AUTH_PLACEHOLDER_USERNAME),
        ])
        plan = _make_plan(tc)
        result = planner._inject_credentials(plan)
        assert len(result.test_cases) == 0


# ============================================================================
# Prompt Engineering — build_planning_prompt
# ============================================================================


class TestBuildPlanningPrompt:
    """Tests for the build_planning_prompt helper."""

    def test_includes_site_model(self):
        prompt = build_planning_prompt(
            site_model_json='{"base_url": "https://example.com", "has_auth": false}',
            coverage_gaps_json="{}",
            config_summary="Categories: functional",
            hints=[],
            max_tests=10,
        )
        assert "https://example.com" in prompt
        assert '"has_auth": false' in prompt

    def test_includes_budget(self):
        prompt = build_planning_prompt(
            site_model_json="{}",
            coverage_gaps_json="{}",
            config_summary="",
            hints=[],
            max_tests=15,
        )
        assert "15" in prompt

    def test_includes_hints_when_provided(self):
        prompt = build_planning_prompt(
            site_model_json="{}",
            coverage_gaps_json="{}",
            config_summary="",
            hints=["Focus on login flows", "Test vault creation"],
            max_tests=10,
        )
        assert "Focus on login flows" in prompt
        assert "Test vault creation" in prompt

    def test_no_hints_section_when_empty(self):
        prompt = build_planning_prompt(
            site_model_json="{}",
            coverage_gaps_json="{}",
            config_summary="",
            hints=[],
            max_tests=10,
        )
        assert "User Hints" not in prompt
