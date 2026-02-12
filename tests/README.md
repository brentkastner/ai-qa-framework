## Test Suite for AI QA Framework

This directory contains comprehensive unit and integration tests for the AI-powered website QA framework.

## Structure

```
tests/
├── conftest.py                      # Shared fixtures and test configuration
├── test_models_config.py            # Configuration model tests
├── test_models_site.py              # Site model tests
├── test_models_test_plan.py         # Test plan model tests
├── test_models_test_result.py       # Test result model tests
├── test_ai_client.py                # AI client tests
├── test_ai_prompts.py               # AI prompts tests
├── test_executor_action_runner.py   # Action runner tests
├── test_executor_assertion_checker.py # Assertion checker tests
├── test_planner_schema_validator.py # Schema validator tests
├── test_coverage_scorer.py          # Coverage scoring tests
├── test_reporter_json_report.py     # JSON report generation tests
├── test_integration.py              # Integration tests
└── README.md                        # This file
```

## Running Tests

### Prerequisites

Install dependencies including test packages:

```bash
pip install -r requirements.txt
```

This installs:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting

### Run All Tests

```bash
pytest
```

### Run Specific Test Files

```bash
pytest tests/test_models_config.py
pytest tests/test_ai_client.py
```

### Run Tests by Category

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run tests requiring browser
pytest -m requires_browser

# Run tests requiring API credentials
pytest -m requires_api
```

### Run with Coverage

```bash
pytest --cov=src --cov-report=html
```

View coverage report: `open htmlcov/index.html`

### Run Specific Tests

```bash
# By test name pattern
pytest -k "test_config"

# By test class
pytest tests/test_models_config.py::TestFrameworkConfig

# Single test
pytest tests/test_models_config.py::TestFrameworkConfig::test_required_fields
```

### Verbose Output

```bash
pytest -v              # Verbose
pytest -vv             # Very verbose
pytest -s              # Show print statements
pytest -x              # Stop on first failure
```

## Test Markers

Tests are marked with categories:

- `@pytest.mark.unit` - Unit tests for individual functions/classes
- `@pytest.mark.integration` - Integration tests for multiple components
- `@pytest.mark.e2e` - End-to-end tests for full workflows
- `@pytest.mark.slow` - Tests that take significant time
- `@pytest.mark.requires_api` - Tests needing API credentials
- `@pytest.mark.requires_browser` - Tests requiring browser automation

## Test Fixtures

Common fixtures available in `conftest.py`:

### Configuration Fixtures
- `viewport_config` - Test viewport configuration
- `crawl_config` - Test crawl configuration
- `auth_config` - Test authentication configuration
- `framework_config` - Complete framework configuration
- `temp_config_file` - Temporary config file

### Model Fixtures
- `element_model` - Test element model
- `form_field` - Test form field
- `form_model` - Test form model
- `page_model` - Test page model
- `site_model` - Test site model
- `action` - Test action
- `assertion` - Test assertion
- `test_case` - Test case
- `test_plan` - Test plan

### Result Fixtures
- `action_result` - Action result
- `assertion_result` - Assertion result
- `step_result` - Step result
- `test_result` - Test result
- `test_run_result` - Test run result

### Mock Fixtures
- `mock_anthropic_client` - Mocked Anthropic AI client
- `mock_page` - Mocked Playwright page
- `mock_context` - Mocked browser context
- `mock_browser` - Mocked browser

### Directory Fixtures
- `temp_evidence_dir` - Temporary evidence directory
- `temp_baseline_dir` - Temporary baseline directory
- `temp_report_dir` - Temporary report directory

## Writing Tests

### Example Unit Test

```python
import pytest
from src.models.config import ViewportConfig

class TestViewportConfig:
    def test_default_values(self):
        """Test ViewportConfig has correct defaults."""
        config = ViewportConfig()
        assert config.width == 1280
        assert config.height == 720
        assert config.name == "desktop"

    def test_custom_values(self):
        """Test ViewportConfig accepts custom values."""
        config = ViewportConfig(width=375, height=812, name="mobile")
        assert config.width == 375
```

### Example Async Test

```python
import pytest
from src.executor.action_runner import run_action
from src.models.test_plan import Action

@pytest.mark.asyncio
class TestRunAction:
    async def test_navigate_action(self, mock_page):
        """Test navigate action."""
        action = Action(
            action_type="navigate",
            value="https://example.com",
        )
        await run_action(mock_page, action)
        mock_page.goto.assert_called_once()
```

### Example Integration Test

```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
class TestExecutorFlow:
    async def test_action_to_assertion_flow(self, mock_page, temp_evidence_dir):
        """Test running actions followed by assertions."""
        from src.executor.action_runner import run_action
        from src.executor.assertion_checker import check_assertion

        # Run action
        action = Action(action_type="navigate", value="https://example.com")
        await run_action(mock_page, action)

        # Check assertion
        assertion = Assertion(assertion_type="url_matches", expected_value="/")
        result = await check_assertion(mock_page, assertion, temp_evidence_dir)

        assert result.passed is True
```

## Test Coverage

Target coverage: **80%+**

Current coverage by module:
- Models: ~95%
- AI Client: ~85%
- Executor: ~80%
- Planner: ~75%
- Reporter: ~70%
- Coverage: ~65%

## Continuous Integration

Tests run automatically on:
- Every commit (via pre-commit hooks)
- Pull requests
- Main branch merges

## Debugging Tests

### Run with debugger

```bash
pytest --pdb  # Drop into debugger on failure
```

### Show local variables on failure

```bash
pytest -l
```

### Capture output

```bash
pytest --capture=no  # or -s
```

### Run last failed tests

```bash
pytest --lf  # last-failed
pytest --ff  # failed-first
```

## Best Practices

1. **One assertion per test** - Keep tests focused
2. **Use descriptive names** - Test names should explain what they test
3. **Arrange-Act-Assert** - Structure tests clearly
4. **Use fixtures** - Reuse common setup code
5. **Mock external dependencies** - Don't call real APIs or browsers in unit tests
6. **Test edge cases** - Empty inputs, None values, errors
7. **Keep tests fast** - Use `@pytest.mark.slow` for long-running tests

## Common Issues

### API Key Required

Some tests require `ANTHROPIC_API_KEY` environment variable:

```bash
export ANTHROPIC_API_KEY=your-key-here
pytest -m requires_api
```

### Async Tests Failing

Ensure `pytest-asyncio` is installed:

```bash
pip install pytest-asyncio
```

### Import Errors

Ensure dependencies are installed:

```bash
pip install -r requirements.txt
```

## Contributing

When adding new features:

1. Write tests first (TDD approach)
2. Ensure all tests pass
3. Maintain or improve coverage
4. Add docstrings to tests
5. Update this README if adding new test categories

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Testing best practices](https://docs.pytest.org/en/stable/goodpractices.html)
