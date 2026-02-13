# Contributing to AI QA Framework

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.12+
- An [Anthropic API key](https://console.anthropic.com/) (for AI-powered features)

### Development Setup

1. **Fork and clone the repository:**

   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-qa-framework.git
   cd ai-qa-framework
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Set up your environment:**

   ```bash
   export ANTHROPIC_API_KEY=your_key_here  # Required for AI features
   ```

5. **Run the tests to verify your setup:**

   ```bash
   python -m pytest
   ```

## How to Contribute

### Reporting Bugs

- Use the [Bug Report](https://github.com/brentkastner/ai-qa-framework/issues/new?template=bug_report.yml) issue template
- Include your Python version, OS, and steps to reproduce
- Attach relevant logs or screenshots if possible

### Suggesting Features

- Use the [Feature Request](https://github.com/brentkastner/ai-qa-framework/issues/new?template=feature_request.yml) issue template
- Describe the problem your feature would solve
- Suggest a possible implementation if you have one in mind

### Submitting Code

1. **Create a branch** from `main`:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**, following the code style conventions below.

3. **Add or update tests** for your changes:

   ```bash
   python -m pytest
   ```

4. **Push your branch** and open a Pull Request against `main`.

## Code Style

- Follow existing patterns in the codebase
- Use type hints for function signatures
- Use Pydantic models for data structures (see `src/models/`)
- Use `async/await` for I/O-bound operations
- Keep functions focused and well-named

## Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=src

# Run specific test markers
python -m pytest -m unit          # Unit tests only
python -m pytest -m integration   # Integration tests only

# Run a specific test file
python -m pytest tests/test_ai_client.py
```

See [tests/README.md](./tests/README.md) for detailed testing documentation.

## Project Structure

```
src/
├── cli.py              # CLI entry point
├── orchestrator.py      # Pipeline coordinator
├── ai/                  # AI integration (Anthropic client, prompts)
├── crawler/             # Site discovery engine
├── planner/             # AI test plan generation
├── executor/            # Test execution with error recovery
├── reporter/            # HTML/JSON report generation
├── coverage/            # Coverage tracking and gap analysis
└── models/              # Pydantic data models
```

## Areas of Interest

We particularly welcome contributions in these areas:

- Additional test categories (accessibility, performance)
- Multi-browser support (Firefox, WebKit)
- Enhanced authentication strategies (OAuth, SAML)
- Custom assertion types
- Improved crawling for complex SPAs
- Documentation improvements

## Questions?

If you have questions about contributing, feel free to open a [Discussion](https://github.com/brentkastner/ai-qa-framework/discussions) or ask in an issue.
