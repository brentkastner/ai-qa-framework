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
