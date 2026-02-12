"""Tests for test plan data structures."""

import pytest

from src.models.test_plan import Action, Assertion, TestCase as TestCaseModel, TestPlan as TestPlanModel


class TestAction:
    """Tests for Action model."""

    def test_minimal_action(self):
        """Test Action with minimal required fields."""
        action = Action(action_type="click")
        assert action.action_type == "click"
        assert action.selector is None
        assert action.value is None
        assert action.description == ""

    def test_click_action(self):
        """Test click action."""
        action = Action(
            action_type="click",
            selector="button#submit",
            description="Click the submit button",
        )
        assert action.action_type == "click"
        assert action.selector == "button#submit"
        assert action.value is None

    def test_fill_action(self):
        """Test fill action with value."""
        action = Action(
            action_type="fill",
            selector="input[name='email']",
            value="test@example.com",
            description="Fill email field",
        )
        assert action.action_type == "fill"
        assert action.value == "test@example.com"

    def test_navigate_action(self):
        """Test navigate action."""
        action = Action(
            action_type="navigate",
            value="https://example.com/page",
            description="Navigate to page",
        )
        assert action.action_type == "navigate"
        assert action.value == "https://example.com/page"

    def test_wait_action(self):
        """Test wait action."""
        action = Action(
            action_type="wait",
            value="2000",
            description="Wait 2 seconds",
        )
        assert action.action_type == "wait"
        assert action.value == "2000"

    def test_screenshot_action(self):
        """Test screenshot action."""
        action = Action(
            action_type="screenshot",
            value="homepage.png",
            description="Take screenshot of homepage",
        )
        assert action.action_type == "screenshot"

    def test_select_action(self):
        """Test select dropdown action."""
        action = Action(
            action_type="select",
            selector="select[name='country']",
            value="USA",
            description="Select country",
        )
        assert action.action_type == "select"

    def test_keyboard_action(self):
        """Test keyboard action."""
        action = Action(
            action_type="keyboard",
            value="Enter",
            description="Press Enter key",
        )
        assert action.action_type == "keyboard"

    def test_serialization(self):
        """Test Action serialization."""
        action = Action(
            action_type="hover",
            selector=".menu-item",
            description="Hover over menu",
        )
        data = action.model_dump()
        assert data["action_type"] == "hover"
        assert data["selector"] == ".menu-item"


class TestAssertion:
    """Tests for Assertion model."""

    def test_minimal_assertion(self):
        """Test Assertion with minimal required fields."""
        assertion = Assertion(assertion_type="element_visible")
        assert assertion.assertion_type == "element_visible"
        assert assertion.selector is None
        assert assertion.expected_value is None
        assert assertion.tolerance is None
        assert assertion.description == ""

    def test_element_visible_assertion(self):
        """Test element_visible assertion."""
        assertion = Assertion(
            assertion_type="element_visible",
            selector=".success-message",
            description="Success message should be visible",
        )
        assert assertion.assertion_type == "element_visible"
        assert assertion.selector == ".success-message"

    def test_element_hidden_assertion(self):
        """Test element_hidden assertion."""
        assertion = Assertion(
            assertion_type="element_hidden",
            selector=".loading-spinner",
            description="Loading spinner should be hidden",
        )
        assert assertion.assertion_type == "element_hidden"

    def test_text_contains_assertion(self):
        """Test text_contains assertion."""
        assertion = Assertion(
            assertion_type="text_contains",
            selector="h1",
            expected_value="Welcome",
            description="Heading should contain 'Welcome'",
        )
        assert assertion.assertion_type == "text_contains"
        assert assertion.expected_value == "Welcome"

    def test_text_equals_assertion(self):
        """Test text_equals assertion."""
        assertion = Assertion(
            assertion_type="text_equals",
            selector=".status",
            expected_value="Active",
        )
        assert assertion.assertion_type == "text_equals"
        assert assertion.expected_value == "Active"

    def test_url_matches_assertion(self):
        """Test url_matches assertion."""
        assertion = Assertion(
            assertion_type="url_matches",
            expected_value="/dashboard",
            description="URL should match dashboard",
        )
        assert assertion.assertion_type == "url_matches"

    def test_screenshot_diff_assertion(self):
        """Test screenshot_diff assertion with tolerance."""
        assertion = Assertion(
            assertion_type="screenshot_diff",
            expected_value="baseline.png",
            tolerance=0.05,
            description="Screenshot should match baseline",
        )
        assert assertion.assertion_type == "screenshot_diff"
        assert assertion.tolerance == 0.05

    def test_element_count_assertion(self):
        """Test element_count assertion."""
        assertion = Assertion(
            assertion_type="element_count",
            selector=".list-item",
            expected_value="5",
            description="Should have 5 list items",
        )
        assert assertion.assertion_type == "element_count"

    def test_network_request_made_assertion(self):
        """Test network_request_made assertion."""
        assertion = Assertion(
            assertion_type="network_request_made",
            expected_value="/api/users",
            description="API call should be made",
        )
        assert assertion.assertion_type == "network_request_made"

    def test_no_console_errors_assertion(self):
        """Test no_console_errors assertion."""
        assertion = Assertion(
            assertion_type="no_console_errors",
            description="No console errors should occur",
        )
        assert assertion.assertion_type == "no_console_errors"

    def test_response_status_assertion(self):
        """Test response_status assertion."""
        assertion = Assertion(
            assertion_type="response_status",
            expected_value="200",
            description="Response should be 200 OK",
        )
        assert assertion.assertion_type == "response_status"
        assert assertion.expected_value == "200"


class TestTestCase:
    """Tests for TestCase model."""

    def test_minimal_test_case(self):
        """Test TestCase with minimal required fields."""
        test = TestCaseModel(
            test_id="test-001",
            name="Basic test",
        )
        assert test.test_id == "test-001"
        assert test.name == "Basic test"
        assert test.description == ""
        assert test.category == "functional"
        assert test.priority == 3
        assert test.target_page_id == ""
        assert test.coverage_signature == ""
        assert test.preconditions == []
        assert test.steps == []
        assert test.assertions == []
        assert test.timeout_seconds == 30

    def test_full_test_case(self):
        """Test TestCase with all fields."""
        precondition = Action(action_type="navigate", value="https://example.com")
        step = Action(action_type="click", selector="#submit")
        assertion = Assertion(assertion_type="element_visible", selector=".success")

        test = TestCaseModel(
            test_id="test-login-001",
            name="Login with valid credentials",
            description="Verify users can log in with valid email and password",
            category="functional",
            priority=1,
            target_page_id="page-login",
            coverage_signature="login_form_submit_valid",
            preconditions=[precondition],
            steps=[step],
            assertions=[assertion],
            timeout_seconds=60,
        )
        assert test.test_id == "test-login-001"
        assert test.priority == 1
        assert len(test.preconditions) == 1
        assert len(test.steps) == 1
        assert len(test.assertions) == 1
        assert test.timeout_seconds == 60

    def test_functional_category(self):
        """Test functional test category."""
        test = TestCaseModel(
            test_id="test-001",
            name="Functional test",
            category="functional",
        )
        assert test.category == "functional"

    def test_visual_category(self):
        """Test visual test category."""
        test = TestCaseModel(
            test_id="test-002",
            name="Visual test",
            category="visual",
        )
        assert test.category == "visual"

    def test_security_category(self):
        """Test security test category."""
        test = TestCaseModel(
            test_id="test-003",
            name="Security test",
            category="security",
        )
        assert test.category == "security"

    def test_priority_levels(self):
        """Test different priority levels."""
        critical = TestCaseModel(test_id="t1", name="Critical", priority=1)
        high = TestCaseModel(test_id="t2", name="High", priority=2)
        medium = TestCaseModel(test_id="t3", name="Medium", priority=3)
        low = TestCaseModel(test_id="t4", name="Low", priority=4)

        assert critical.priority == 1
        assert high.priority == 2
        assert medium.priority == 3
        assert low.priority == 4

    def test_multiple_steps(self):
        """Test TestCase with multiple steps."""
        steps = [
            Action(action_type="fill", selector="#email", value="test@example.com"),
            Action(action_type="fill", selector="#password", value="secret"),
            Action(action_type="click", selector="#submit"),
        ]
        test = TestCaseModel(
            test_id="test-001",
            name="Multi-step test",
            steps=steps,
        )
        assert len(test.steps) == 3

    def test_multiple_assertions(self):
        """Test TestCase with multiple assertions."""
        assertions = [
            Assertion(assertion_type="url_matches", expected_value="/dashboard"),
            Assertion(assertion_type="element_visible", selector=".welcome"),
            Assertion(assertion_type="no_console_errors"),
        ]
        test = TestCaseModel(
            test_id="test-001",
            name="Multi-assertion test",
            assertions=assertions,
        )
        assert len(test.assertions) == 3


class TestTestPlan:
    """Tests for TestPlan model."""

    def test_minimal_test_plan(self):
        """Test TestPlan with minimal required fields."""
        plan = TestPlanModel(
            plan_id="plan-001",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
        )
        assert plan.plan_id == "plan-001"
        assert plan.generated_at == "2025-01-01T00:00:00Z"
        assert plan.target_url == "https://example.com"
        assert plan.test_cases == []
        assert plan.estimated_duration_seconds == 0
        assert plan.coverage_intent == {}

    def test_plan_with_test_cases(self):
        """Test TestPlan with test cases."""
        tests = [
            TestCaseModel(test_id="t1", name="Test 1"),
            TestCaseModel(test_id="t2", name="Test 2"),
            TestCaseModel(test_id="t3", name="Test 3"),
        ]
        plan = TestPlanModel(
            plan_id="plan-001",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=tests,
        )
        assert len(plan.test_cases) == 3
        assert plan.test_cases[0].test_id == "t1"

    def test_plan_with_duration_estimate(self):
        """Test TestPlan with estimated duration."""
        plan = TestPlanModel(
            plan_id="plan-001",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            estimated_duration_seconds=300,
        )
        assert plan.estimated_duration_seconds == 300

    def test_plan_with_coverage_intent(self):
        """Test TestPlan with coverage intent metadata."""
        coverage = {
            "pages_covered": ["page-1", "page-2"],
            "features_tested": ["login", "signup"],
        }
        plan = TestPlanModel(
            plan_id="plan-001",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            coverage_intent=coverage,
        )
        assert "pages_covered" in plan.coverage_intent
        assert len(plan.coverage_intent["pages_covered"]) == 2

    def test_serialization(self):
        """Test TestPlan serialization."""
        test = TestCaseModel(test_id="t1", name="Test 1")
        plan = TestPlanModel(
            plan_id="plan-001",
            generated_at="2025-01-01T00:00:00Z",
            target_url="https://example.com",
            test_cases=[test],
        )
        data = plan.model_dump()
        assert data["plan_id"] == "plan-001"
        assert len(data["test_cases"]) == 1
