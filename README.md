# AI QA Framework

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/brentkastner/ai-qa-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/brentkastner/ai-qa-framework/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Give it a URL. Get comprehensive test coverage.**

An autonomous AI-driven QA framework that automatically discovers, tests, and reports on any website—no manual test writing required.

```bash
# Install
pip install -r requirements.txt
playwright install chromium

# Configure
python -m src.cli init --target https://yoursite.com

# Run
export ANTHROPIC_API_KEY=your_key_here
python -m src.cli run
```

**That's it.** The framework will crawl your site, generate intelligent tests using Claude AI, execute them with smart error recovery, and produce detailed reports.

---

## What Makes This Different?

- **Zero test scripts** - AI generates tests by understanding your site
- **Self-healing** - When selectors break, AI analyzes screenshots and fixes them
- **Comprehensive coverage** - Functional, visual, and security testing in one pass
- **Natural language hints** - Guide priorities without writing test specs
- **Coverage memory** - Tracks what's been tested, focuses on gaps

**→ [Read the full overview](./OVERVIEW.md)** to understand how it works and why it exists.

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Set Up Configuration

Create `qa-config.json`:

```json
{
  "target_url": "https://yoursite.com",
  "categories": ["functional", "visual", "security"],
  "hints": [
    "The checkout flow is our most critical path"
  ]
}
```

Or use the CLI:

```bash
python -m src.cli init --target https://yoursite.com
```

### 3. Run Tests

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here

# Run the full pipeline
python -m src.cli run

# View the report
open qa-reports/report_*.html
```

---

## How It Works

**Four-stage pipeline:**

1. **Crawl** - Real browser discovers pages, forms, elements, and APIs
2. **Plan** - Claude AI analyzes structure and generates contextual tests
3. **Execute** - Playwright runs tests with AI-assisted error recovery
4. **Report** - HTML/JSON reports with screenshots and AI insights

**→ [See detailed architecture](./REQUIREMENTS.md#core-architecture)**

## Key Features

### Autonomous Testing
- **Zero manual test writing** - AI generates contextual tests automatically
- **Self-healing tests** - AI recovers from selector changes
- **Coverage tracking** - Remembers what's been tested, targets gaps
- **Regression detection** - Automatically catches pass→fail transitions

### AI-Powered Intelligence
- **Test generation** - Claude analyzes your site to create relevant tests
- **Error recovery** - Analyzes screenshots to fix broken selectors
- **Natural language summaries** - Explains findings in plain English
- **Hint-based prioritization** - Guide testing with simple phrases

### Comprehensive Coverage
- **Functional tests** - Forms, navigation, workflows, CRUD
- **Visual regression** - Screenshot baselines, responsive design
- **Security checks** - XSS, HTTPS, cookies, headers
- **Evidence collection** - Screenshots, logs, network activity

**→ [See all features in detail](./OVERVIEW.md#key-features)**

---

## Configuration

### Basic Configuration

```json
{
  "target_url": "https://yoursite.com"
}
```

### With Authentication

```json
{
  "target_url": "https://yoursite.com",
  "auth": {
    "login_url": "https://yoursite.com/login",
    "username": "testuser@example.com",
    "password": "env:QA_TEST_PASSWORD"
  }
}
```

### With Natural Language Hints

```json
{
  "target_url": "https://yoursite.com",
  "hints": [
    "The checkout flow is our most critical path",
    "Search has been buggy with special characters",
    "We just redesigned the pricing page"
  ]
}
```

Hints guide AI priorities without writing test specifications. The AI interprets them and adjusts test generation accordingly.

**→ [Complete configuration reference](./REQUIREMENTS.md#configuration)**

## CLI Commands

### Pipeline Operations

```bash
# Full pipeline (recommended)
python -m src.cli run

# Individual stages
python -m src.cli crawl                          # Discover site
python -m src.cli plan                           # Generate tests
python -m src.cli execute --plan-file <path>     # Run tests
```

### Coverage Management

```bash
# View coverage statistics
python -m src.cli coverage

# Find untested or stale areas
python -m src.cli coverage --gaps

# Reset coverage history
python -m src.cli coverage --reset
```

### Hint Management

```bash
# Guide AI priorities with natural language
python -m src.cli hint add "Checkout flow is critical"
python -m src.cli hint list
python -m src.cli hint clear
```

**→ [Complete CLI reference](./REQUIREMENTS.md#cli-interface)**

---

## Documentation

### For Everyone
- **[OVERVIEW.md](./OVERVIEW.md)** - What this is, why it exists, how it works
- **[README.md](./README.md)** - Quick start guide (you are here)

### For Developers
- **[REQUIREMENTS.md](./REQUIREMENTS.md)** - Complete technical specification
- **[OriginalSpec.md](./OriginalSpec.md)** - Original design document

### Topics
- [Architecture & Components](./REQUIREMENTS.md#core-architecture)
- [Configuration Options](./REQUIREMENTS.md#configuration)
- [Test Types & Assertions](./REQUIREMENTS.md#test-types--assertions)
- [AI Integration Details](./REQUIREMENTS.md#ai-integration)
- [Coverage System](./REQUIREMENTS.md#reporting--coverage)
- [Extending the Framework](./REQUIREMENTS.md#extensibility)

---

## Requirements

- **Python 3.12+**
- **Chromium** (via `playwright install chromium`)
- **Anthropic API key** (optional but recommended)

### Environment Variables

```bash
export ANTHROPIC_API_KEY=your_key_here    # For AI features
export QA_TEST_PASSWORD=secret            # For auth (if needed)
```

**Without an API key**, the framework operates in fallback mode:
- Basic test generation (template-based)
- No AI summaries or error recovery
- All execution features remain available

**→ [Technical specifications](./REQUIREMENTS.md#technical-specifications)**

---

## What Gets Generated

After running `python -m src.cli run`, you'll have:

```
.qa-framework/
├── site_model/model.json          # Discovered site structure
├── coverage/registry.json         # Test coverage history
└── latest_plan.json               # Generated test plan

qa-reports/
├── report_run_*.html              # Interactive HTML report
└── report_run_*.json              # Machine-readable results
```

**Open the HTML report** to see:
- Pass/fail statistics with visual breakdown
- AI-generated natural language summary
- Step-by-step test execution with screenshots
- Regression detection
- Coverage metrics

---

## Real-World Example

Testing an e-commerce site:

```bash
# 1. Initialize
python -m src.cli init --target https://myshop.com

# 2. Add priority hints
python -m src.cli hint add "Checkout flow is business-critical"
python -m src.cli hint add "Product search has been unreliable"

# 3. Run tests
export ANTHROPIC_API_KEY=your_key
python -m src.cli run

# 4. Review results
open qa-reports/report_*.html
```

**What happens:**
- Crawls homepage, products, cart, checkout (5-10 min)
- AI generates ~25 relevant tests (30-60 sec)
- Executes tests with smart recovery (10-20 min)
- Creates detailed report with insights

**Example findings:**
- "Add to cart" button selector changed → AI auto-fixed
- XSS vulnerability in product review form → Flagged
- Visual regression: Logo alignment shifted → Screenshot diff
- Checkout flow: 100% passing

**→ [See full example walkthrough](./OVERVIEW.md#real-world-example)**

---

## Who Is This For?

**Development Teams** - Get comprehensive testing without maintaining test scripts

**QA Engineers** - Focus on strategy while AI handles test generation

**Solo Developers** - Enterprise-level QA without a dedicated team

**Anyone who wants** - Continuous, intelligent testing that adapts to change

**→ [Learn more about use cases](./OVERVIEW.md#who-is-this-for)**

---

## Contributing

We welcome contributions! See the [Contributing Guide](./CONTRIBUTING.md) for how to get started.

Areas of interest:
- Additional test categories (accessibility, performance)
- Multi-browser support (Firefox, WebKit)
- Enhanced authentication (OAuth, SAML)
- Custom assertion types

Please report security vulnerabilities via the process described in [SECURITY.md](./SECURITY.md).

---

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](./LICENSE) file for details.

---

## Get Started

Ready to test your site?

```bash
pip install -r requirements.txt
playwright install chromium
python -m src.cli init --target https://yoursite.com
export ANTHROPIC_API_KEY=your_key_here
python -m src.cli run
```

**Questions?** Read [OVERVIEW.md](./OVERVIEW.md) for a comprehensive introduction or [REQUIREMENTS.md](./REQUIREMENTS.md) for technical details.
