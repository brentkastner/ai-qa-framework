"""Pytest configuration and shared fixtures."""

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from playwright.async_api import Browser, BrowserContext, Page

from src.models.config import (
    AuthConfig,
    CrawlConfig,
    FrameworkConfig,
    ViewportConfig,
)
from src.models.site_model import (
    APIEndpoint,
    ElementModel,
    FormField,
    FormModel,
    PageModel,
    SiteModel,
)
from src.models.test_plan import Action, Assertion, TestCase, TestPlan
from src.models.test_result import (
    AssertionResult,
    Evidence,
    FallbackRecord,
    RunResult,
    StepResult,
    TestResult,
)


# ============================================================================
# Configuration Fixtures
# ============================================================================


@pytest.fixture
def viewport_config() -> ViewportConfig:
    """Create a test viewport configuration."""
    return ViewportConfig(width=1280, height=720, name="desktop")


@pytest.fixture
def crawl_config(viewport_config: ViewportConfig) -> CrawlConfig:
    """Create a test crawl configuration."""
    return CrawlConfig(
        target_url="https://example.com",
        max_pages=10,
        max_depth=3,
        include_patterns=["*/products/*"],
        exclude_patterns=["*/admin/*"],
        wait_for_idle=True,
        viewport=viewport_config,
    )


@pytest.fixture
def auth_config() -> AuthConfig:
    """Create a test authentication configuration."""
    return AuthConfig(
        login_url="https://example.com/login",
        username="test@example.com",
        password="testpass123",
        username_selector="input[name='email']",
        password_selector="input[name='password']",
        submit_selector="button[type='submit']",
        success_indicator=".dashboard",
    )


@pytest.fixture
def framework_config(crawl_config: CrawlConfig) -> FrameworkConfig:
    """Create a test framework configuration."""
    return FrameworkConfig(
        target_url="https://example.com",
        crawl=crawl_config,
        categories=["functional", "visual"],
        max_tests_per_run=50,
        max_execution_time_seconds=1800,
        max_parallel_contexts=3,
        ai_model="claude-opus-4-6",
        ai_max_fallback_calls_per_test=3,
        ai_max_planning_tokens=32000,
        visual_diff_tolerance=0.15,
        report_output_dir="./test-reports",
    )


@pytest.fixture
def temp_config_file(framework_config: FrameworkConfig, tmp_path: Path) -> Path:
    """Create a temporary config file."""
    config_file = tmp_path / "test-config.json"
    framework_config.save(config_file)
    return config_file


# ============================================================================
# Site Model Fixtures
# ============================================================================


@pytest.fixture
def element_model() -> ElementModel:
    """Create a test element model."""
    return ElementModel(
        element_id="btn-submit",
        tag="button",
        selector="button#submit",
        role="button",
        text_content="Submit",
        is_interactive=True,
        element_type="button",
        attributes={"id": "submit", "class": "btn btn-primary"},
    )


@pytest.fixture
def form_field() -> FormField:
    """Create a test form field."""
    return FormField(
        name="email",
        field_type="email",
        required=True,
        validation_pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        selector="input[name='email']",
    )


@pytest.fixture
def form_model(form_field: FormField) -> FormModel:
    """Create a test form model."""
    return FormModel(
        form_id="login-form",
        action="/api/login",
        method="POST",
        fields=[form_field],
        submit_selector="button[type='submit']",
    )


@pytest.fixture
def page_model(element_model: ElementModel, form_model: FormModel) -> PageModel:
    """Create a test page model."""
    return PageModel(
        page_id="page-login",
        url="https://example.com/login",
        page_type="form",
        title="Login Page",
        elements=[element_model],
        forms=[form_model],
    )


@pytest.fixture
def site_model(page_model: PageModel) -> SiteModel:
    """Create a test site model."""
    return SiteModel(
        base_url="https://example.com",
        pages=[page_model],
        navigation_graph={"page-login": ["page-dashboard"]},
        api_endpoints=[
            APIEndpoint(
                url="/api/login",
                method="POST",
                request_content_type="application/json",
                response_content_type="application/json",
                status_codes_seen=[200, 401],
            )
        ],
    )


# ============================================================================
# Test Plan Fixtures
# ============================================================================


@pytest.fixture
def action() -> Action:
    """Create a test action."""
    return Action(
        action_type="click",
        selector="button#submit",
        value=None,
        description="Click the submit button",
    )


@pytest.fixture
def assertion() -> Assertion:
    """Create a test assertion."""
    return Assertion(
        assertion_type="element_visible",
        selector=".success-message",
        expected_value=None,
        description="Success message should be visible",
    )


@pytest.fixture
def test_case(action: Action, assertion: Assertion) -> TestCase:
    """Create a test case."""
    return TestCase(
        test_id="test-001",
        name="Login with valid credentials",
        description="Test that users can log in with valid credentials",
        category="functional",
        priority=1,
        target_page_id="page-login",
        coverage_signature="login_form_submit",
        steps=[action],
        assertions=[assertion],
        timeout_seconds=30,
    )


@pytest.fixture
def test_plan(test_case: TestCase) -> TestPlan:
    """Create a test plan."""
    return TestPlan(
        plan_id="plan-001",
        generated_at="2025-01-01T00:00:00Z",
        target_url="https://example.com",
        test_cases=[test_case],
        estimated_duration_seconds=60,
    )


# ============================================================================
# Test Result Fixtures
# ============================================================================


@pytest.fixture
def step_result() -> StepResult:
    """Create a test step result."""
    return StepResult(
        step_index=0,
        action_type="click",
        selector="button#submit",
        value=None,
        description="Click submit button",
        status="pass",
        error_message=None,
        screenshot_path=None,
    )


@pytest.fixture
def assertion_result() -> AssertionResult:
    """Create a test assertion result."""
    return AssertionResult(
        assertion_type="element_visible",
        selector=".success-message",
        expected_value=None,
        description="Success message should be visible",
        passed=True,
        actual_value="visible",
        message="Element is visible as expected",
    )


@pytest.fixture
def test_result(step_result: StepResult, assertion_result: AssertionResult) -> TestResult:
    """Create a test result."""
    return TestResult(
        test_id="test-001",
        test_name="Login with valid credentials",
        description="Test login functionality",
        category="functional",
        priority=1,
        result="pass",
        duration_seconds=0.5,
        step_results=[step_result],
        assertion_results=[assertion_result],
        assertions_passed=1,
        assertions_total=1,
        evidence=Evidence(),
    )


@pytest.fixture
def run_result(test_result: TestResult) -> RunResult:
    """Create a test run result."""
    return RunResult(
        run_id="run-001",
        plan_id="plan-001",
        started_at="2025-01-01T00:00:00Z",
        completed_at="2025-01-01T00:05:00Z",
        target_url="https://example.com",
        total_tests=1,
        passed=1,
        failed=0,
        skipped=0,
        errors=0,
        duration_seconds=300.0,
        test_results=[test_result],
        ai_summary="All tests passed successfully.",
    )


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_anthropic_client() -> Mock:
    """Create a mock Anthropic client."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.content = [Mock(text='{"test": "response"}')]
    mock_response.stop_reason = "end_turn"
    mock_response.usage = Mock(input_tokens=100, output_tokens=200)
    mock_client.messages.create.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_page() -> AsyncMock:
    """Create a mock Playwright page."""
    page = AsyncMock(spec=Page)
    page.url = "https://example.com"
    page.title.return_value = "Example Page"
    page.screenshot = AsyncMock()
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.locator.return_value = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.keyboard = AsyncMock()
    page.keyboard.press = AsyncMock()
    return page


@pytest.fixture
def mock_context() -> AsyncMock:
    """Create a mock Playwright browser context."""
    context = AsyncMock(spec=BrowserContext)
    context.new_page = AsyncMock()
    return context


@pytest.fixture
def mock_browser() -> AsyncMock:
    """Create a mock Playwright browser."""
    browser = AsyncMock(spec=Browser)
    browser.new_context = AsyncMock()
    return browser


# ============================================================================
# Temporary Directory Fixtures
# ============================================================================


@pytest.fixture
def temp_evidence_dir(tmp_path: Path) -> Path:
    """Create a temporary evidence directory."""
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    return evidence_dir


@pytest.fixture
def temp_baseline_dir(tmp_path: Path) -> Path:
    """Create a temporary baseline directory."""
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    return baseline_dir


@pytest.fixture
def temp_report_dir(tmp_path: Path) -> Path:
    """Create a temporary report directory."""
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    return report_dir


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_dom_html() -> str:
    """Create a mock DOM HTML string for testing."""
    return """
    <html>
        <body>
            <div class="header">
                <h1>Test Page</h1>
            </div>
            <div class="content">
                <button id="submit">Submit</button>
                <input name="email" type="email" />
            </div>
        </body>
    </html>
    """


def create_mock_screenshot(path: Path) -> None:
    """Create a mock screenshot file for testing."""
    # Create a simple 1x1 pixel PNG
    png_data = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
        b'\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-'
        b'\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    path.write_bytes(png_data)


@pytest.fixture
def create_screenshot_helper():
    """Fixture that provides the create_mock_screenshot function."""
    return create_mock_screenshot


# ============================================================================
# AI Client Fixtures
# ============================================================================


@pytest.fixture
def mock_ai_client() -> Mock:
    """Create a mock AIClient for ai_evaluate assertions.

    Default behavior: returns a passing verdict with high confidence.
    Override complete_with_image.return_value in individual tests to customize.
    """
    client = Mock()
    client.complete_with_image = Mock(
        return_value='{"passed": true, "confidence": 0.95, "reasoning": "Intent satisfied"}'
    )
    return client
