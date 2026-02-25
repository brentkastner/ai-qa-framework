"""Tests for test plan schema validation."""

import pytest

from src.planner.schema_validator import validate_test_plan
from src.models.test_plan import Action, Assertion, TestCase as TestCaseModel, TestPlan as TestPlanModel


class TestValidateTestPlan:
    """Tests for validate_test_plan function."""

    def test_empty_test_plan_fails(self):
        """Test validation fails for test plan with no test cases."""
        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[],
        )

        errors = validate_test_plan(plan)

        assert len(errors) > 0
        assert any("no test cases" in e.lower() for e in errors)

    def test_valid_test_plan_passes(self):
        """Test validation passes for valid test plan."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Valid Test",
            category="functional",
            priority=1,
            steps=[Action(action_type="navigate", value="https://example.com")],
            assertions=[Assertion(assertion_type="url_matches", expected_value="/")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert len(errors) == 0

    def test_duplicate_test_ids_fail(self):
        """Test validation fails for duplicate test IDs."""
        test1 = TestCaseModel(
            test_id="test-1",
            name="Test 1",
            category="functional",
            steps=[Action(action_type="wait", value="1000")],
        )
        test2 = TestCaseModel(
            test_id="test-1",  # Duplicate ID
            name="Test 2",
            category="functional",
            steps=[Action(action_type="wait", value="1000")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test1, test2],
        )

        errors = validate_test_plan(plan)

        assert any("duplicate" in e.lower() and "test-1" in e for e in errors)

    def test_invalid_category_fails(self):
        """Test validation fails for invalid category."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="invalid_category",
            steps=[Action(action_type="wait", value="1000")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("invalid category" in e.lower() for e in errors)

    def test_valid_categories_pass(self):
        """Test all valid categories pass validation."""
        categories = ["functional", "visual", "security"]

        for category in categories:
            test_case = TestCaseModel(
                test_id=f"test-{category}",
                name="Test",
                category=category,
                steps=[Action(action_type="wait", value="1000")],
            )

            plan = TestPlanModel(
                plan_id="plan-1",
                generated_at="2025-01-01T00:00:00Z",
                target_url="https://example.com",
                test_cases=[test_case],
            )

            errors = validate_test_plan(plan)
            # Should not have category error
            assert not any("invalid category" in e.lower() for e in errors)

    def test_invalid_priority_fails(self):
        """Test validation fails for priority out of range."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="functional",
            priority=10,  # Invalid (should be 1-5)
            steps=[Action(action_type="wait", value="1000")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("priority" in e.lower() for e in errors)

    def test_valid_priorities_pass(self):
        """Test priorities 1-5 all pass validation."""
        for priority in range(1, 6):
            test_case = TestCaseModel(
                test_id=f"test-{priority}",
                name="Test",
                category="functional",
                priority=priority,
                steps=[Action(action_type="wait", value="1000")],
            )

            plan = TestPlanModel(
                plan_id="plan-1",
                generated_at="2025-01-01T00:00:00Z",
                target_url="https://example.com",
                test_cases=[test_case],
            )

            errors = validate_test_plan(plan)
            # Should not have priority error
            assert not any("priority" in e.lower() for e in errors)

    def test_no_steps_fails(self):
        """Test validation fails when test case has no steps."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="functional",
            steps=[],  # No steps
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("no steps" in e.lower() for e in errors)

    def test_invalid_action_type_fails(self):
        """Test validation fails for invalid action type."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="functional",
            steps=[Action(action_type="invalid_action")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("invalid action_type" in e.lower() for e in errors)

    def test_all_valid_action_types_pass(self):
        """Test all valid action types pass validation."""
        action_types = [
            "navigate",
            "click",
            "fill",
            "select",
            "hover",
            "scroll",
            "wait",
            "screenshot",
            "keyboard",
        ]

        for action_type in action_types:
            # Provide required fields for actions that need them
            if action_type in ["click", "fill", "select", "hover"]:
                action = Action(
                    action_type=action_type,
                    selector="button",
                    value="value" if action_type == "fill" else None,
                )
            else:
                action = Action(action_type=action_type)

            test_case = TestCaseModel(
                test_id=f"test-{action_type}",
                name="Test",
                category="functional",
                steps=[action],
            )

            plan = TestPlanModel(
                plan_id="plan-1",
                generated_at="2025-01-01T00:00:00Z",
                target_url="https://example.com",
                test_cases=[test_case],
            )

            errors = validate_test_plan(plan)
            # Should not have action_type error
            assert not any("invalid action_type" in e.lower() for e in errors)

    def test_click_without_selector_fails(self):
        """Test click action without selector fails."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="functional",
            steps=[Action(action_type="click")],  # Missing selector
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("click" in e.lower() and "selector" in e.lower() for e in errors)

    def test_fill_without_value_fails(self):
        """Test fill action without value fails."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="functional",
            steps=[
                Action(action_type="fill", selector="input")  # Missing value
            ],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("fill" in e.lower() and "value" in e.lower() for e in errors)

    def test_selector_required_actions_fail_without_selector(self):
        """Test all actions requiring selector fail without it."""
        selector_actions = ["click", "fill", "select", "hover"]

        for action_type in selector_actions:
            test_case = TestCaseModel(
                test_id=f"test-{action_type}",
                name="Test",
                category="functional",
                steps=[
                    Action(
                        action_type=action_type,
                        value="value" if action_type == "fill" else None,
                    )
                ],
            )

            plan = TestPlanModel(
                plan_id="plan-1",
                generated_at="2025-01-01T00:00:00Z",
                target_url="https://example.com",
                test_cases=[test_case],
            )

            errors = validate_test_plan(plan)
            assert any("selector" in e.lower() for e in errors), \
                f"{action_type} should require selector"

    def test_invalid_assertion_type_fails(self):
        """Test validation fails for invalid assertion type."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="functional",
            steps=[Action(action_type="wait", value="1000")],
            assertions=[Assertion(assertion_type="invalid_assertion")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("invalid" in e.lower() and "assertion" in e.lower() for e in errors)

    def test_all_valid_assertion_types_pass(self):
        """Test all valid assertion types pass validation."""
        assertion_types = [
            "element_visible",
            "element_hidden",
            "text_contains",
            "text_equals",
            "text_matches",
            "url_matches",
            "screenshot_diff",
            "element_count",
            "network_request_made",
            "no_console_errors",
            "response_status",
            "ai_evaluate",
        ]

        for assertion_type in assertion_types:
            test_case = TestCaseModel(
                test_id=f"test-{assertion_type}",
                name="Test",
                category="functional",
                steps=[Action(action_type="wait", value="1000")],
                assertions=[Assertion(assertion_type=assertion_type)],
            )

            plan = TestPlanModel(
                plan_id="plan-1",
                generated_at="2025-01-01T00:00:00Z",
                target_url="https://example.com",
                test_cases=[test_case],
            )

            errors = validate_test_plan(plan)
            # Should not have assertion type error
            assert not any(
                "invalid" in e.lower() and "assertion" in e.lower() for e in errors
            )

    def test_preconditions_validated(self):
        """Test preconditions are validated like regular steps."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="functional",
            preconditions=[Action(action_type="invalid_action")],
            steps=[Action(action_type="wait", value="1000")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        assert any("invalid action_type" in e.lower() for e in errors)

    def test_multiple_errors_returned(self):
        """Test all errors are collected and returned."""
        test_case = TestCaseModel(
            test_id="test-1",
            name="Test",
            category="invalid_category",
            priority=10,
            steps=[Action(action_type="invalid_action")],
            assertions=[Assertion(assertion_type="invalid_assertion")],
        )

        plan = TestPlanModel(
            plan_id="plan-1",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test_case],
        )

        errors = validate_test_plan(plan)

        # Should have multiple errors
        assert len(errors) >= 3
        assert any("category" in e.lower() for e in errors)
        assert any("priority" in e.lower() for e in errors)
        assert any("action_type" in e.lower() for e in errors)


class TestValidateApiTests:
    """Tests for API-specific validation rules."""

    def _make_api_plan(self, test_cases):
        return TestPlanModel(
            plan_id="plan-api",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=test_cases,
        )

    def test_valid_api_test_passes(self):
        tc = TestCaseModel(
            test_id="tc_api_001",
            name="[GET] List users",
            category="api",
            steps=[Action(
                action_type="api_get",
                selector="http://localhost/api/users",
            )],
            assertions=[Assertion(
                assertion_type="response_status",
                expected_value="200",
            )],
        )
        errors = validate_test_plan(self._make_api_plan([tc]))
        assert errors == []

    def test_all_api_action_types_are_valid(self):
        for method in ("api_get", "api_post", "api_put", "api_delete", "api_patch"):
            tc = TestCaseModel(
                test_id=f"tc_{method}",
                name=f"[{method.split('_')[1].upper()}] test",
                category="api",
                steps=[Action(action_type=method, selector="http://localhost/api/x")],
                assertions=[Assertion(assertion_type="response_status", expected_value="200")],
            )
            errors = validate_test_plan(self._make_api_plan([tc]))
            assert not any("invalid action_type" in e.lower() for e in errors), \
                f"{method} should be a valid action type"

    def test_all_api_assertion_types_are_valid(self):
        for atype in ("response_status", "response_body_contains", "response_json_path", "response_header"):
            tc = TestCaseModel(
                test_id=f"tc_{atype}",
                name="[GET] test",
                category="api",
                steps=[Action(action_type="api_get", selector="http://localhost/api/x")],
                assertions=[Assertion(assertion_type=atype, selector="key", expected_value="val")],
            )
            errors = validate_test_plan(self._make_api_plan([tc]))
            assert not any("invalid" in e.lower() and "assertion" in e.lower() for e in errors), \
                f"{atype} should be a valid assertion type"

    def test_api_action_without_url_fails(self):
        tc = TestCaseModel(
            test_id="tc_no_url",
            name="[GET] missing url",
            category="api",
            steps=[Action(action_type="api_get", selector=None)],
            assertions=[Assertion(assertion_type="response_status", expected_value="200")],
        )
        errors = validate_test_plan(self._make_api_plan([tc]))
        assert any("requires a url" in e.lower() for e in errors)

    def test_api_test_name_without_bracket_format_fails(self):
        tc = TestCaseModel(
            test_id="tc_bad_name",
            name="Get all users",  # missing [METHOD] prefix
            category="api",
            steps=[Action(action_type="api_get", selector="http://localhost/api/users")],
            assertions=[Assertion(assertion_type="response_status", expected_value="200")],
        )
        errors = validate_test_plan(self._make_api_plan([tc]))
        assert any("[method]" in e.lower() for e in errors)

    def test_api_test_with_correct_name_format_passes(self):
        for name in ["[GET] List items", "[POST] Create user", "[DELETE] Remove item", "[PATCH] Update"]:
            tc = TestCaseModel(
                test_id=f"tc_{name[:5]}",
                name=name,
                category="api",
                steps=[Action(action_type="api_get", selector="http://localhost/api/x")],
                assertions=[Assertion(assertion_type="response_status", expected_value="200")],
            )
            errors = validate_test_plan(self._make_api_plan([tc]))
            assert not any("[method]" in e.lower() for e in errors), \
                f"Name '{name}' should pass format check"

    def test_api_test_with_browser_assertion_fails(self):
        tc = TestCaseModel(
            test_id="tc_bad_assert",
            name="[GET] bad assertion",
            category="api",
            steps=[Action(action_type="api_get", selector="http://localhost/api/x")],
            assertions=[Assertion(assertion_type="element_visible", selector=".foo")],
        )
        errors = validate_test_plan(self._make_api_plan([tc]))
        assert any("browser assertion" in e.lower() for e in errors)

    def test_api_test_actions_in_preconditions_only_no_step_error(self):
        """API test with actions only in preconditions should not raise 'no steps defined'."""
        tc = TestCaseModel(
            test_id="tc_precond_only",
            name="[GET] preconditions only",
            category="api",
            preconditions=[Action(action_type="api_get", selector="http://localhost/api/x")],
            steps=[],
            assertions=[Assertion(assertion_type="response_status", expected_value="200")],
        )
        errors = validate_test_plan(self._make_api_plan([tc]))
        assert not any("no steps" in e.lower() for e in errors)

    def test_api_category_detected_via_action_type(self):
        """A test with api_* actions but category='functional' is still treated as API for validation."""
        tc = TestCaseModel(
            test_id="tc_mislabeled",
            name="Get users",  # wrong format — should be flagged
            category="functional",
            steps=[Action(action_type="api_get", selector="http://localhost/api/users")],
            assertions=[Assertion(assertion_type="response_status", expected_value="200")],
        )
        errors = validate_test_plan(self._make_api_plan([tc]))
        # Should flag the name format issue because it detected api actions
        assert any("[method]" in e.lower() for e in errors)
