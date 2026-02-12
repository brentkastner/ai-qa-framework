# AI QA Framework: Autonomous Website Testing

> **Give it a URL. Get comprehensive test coverage.**

This framework uses AI to autonomously discover, test, and report on any website—no manual test writing required.

---

## What Is This?

The AI QA Framework is an **intelligent testing system** that automatically:

1. **Explores your website** to understand its structure
2. **Generates relevant tests** using AI that understands your site
3. **Runs tests automatically** with smart error recovery
4. **Reports findings** with actionable insights

Think of it as a QA engineer that never sleeps, continuously learning about your site and finding issues before your users do.

---

## Why Does This Exist?

### The Problem

Traditional QA testing requires:
- Writing and maintaining hundreds of test scripts
- Manually updating selectors when UI changes
- Deciding what to test and how to test it
- Keeping tests in sync with rapid development

**This is expensive, time-consuming, and often incomplete.**

### The Solution

Instead of writing tests, you provide:
- A target URL
- Optional authentication credentials
- Natural language hints about what matters to you

**The framework handles everything else.**

It uses Claude AI to understand your website like a human tester would, then generates and executes comprehensive tests automatically.

---

## How It Works

### The Four-Stage Pipeline

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ CRAWL   │ -> │ PLAN    │ -> │ EXECUTE │ -> │ REPORT  │
│ Site    │    │ Tests   │    │ Tests   │    │ Results │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
```

#### 1. Crawl: Intelligent Site Discovery

The framework uses a real browser to explore your website:
- Follows links and discovers pages
- Identifies forms, buttons, and interactive elements
- Detects navigation patterns
- Captures API endpoints
- Takes baseline screenshots

**Works with**: Server-rendered sites, Single Page Applications (React, Vue, Angular), and hybrid apps.

#### 2. Plan: AI-Powered Test Generation

Claude AI analyzes the site structure and creates a test plan:
- Generates contextually relevant tests
- Balances functional, visual, and security testing
- Prioritizes critical paths (checkout, login, etc.)
- Fills in coverage gaps from previous runs
- Incorporates your natural language hints

**Test Categories**:
- **Functional** (50%): Forms, navigation, workflows, CRUD operations
- **Visual** (30%): Layout consistency, responsive design, regression detection
- **Security** (20%): XSS protection, HTTPS, cookie security, error handling

#### 3. Execute: Smart Test Running

Tests run with intelligent failure handling:
- Playwright browser automation for realistic testing
- AI fallback when elements can't be found (analyzes screenshots to suggest fixes)
- Evidence collection (screenshots, console logs, network activity)
- Parallel execution for speed

**If something breaks**, the AI:
- Analyzes the screenshot to understand the page state
- Suggests corrected selectors or alternative actions
- Decides whether to retry, adapt, or skip

#### 4. Report: Actionable Insights

Beautiful, comprehensive reports in HTML and JSON:
- Pass/fail/skip statistics with visual breakdown
- AI-generated natural language summary of findings
- Step-by-step execution details with screenshots
- Regression detection (tests that used to pass but now fail)
- Coverage metrics showing what's tested and what's not

---

## Key Features

### Truly Autonomous

**Zero test scripts required.** The framework:
- Discovers pages automatically
- Decides what to test
- Generates assertions
- Maintains itself as your site evolves

### AI-Assisted Everything

**Three AI touchpoints**:
1. **Planning**: Generates intelligent, contextual tests
2. **Execution**: Recovers from failures by analyzing screenshots
3. **Reporting**: Explains findings in natural language

### Coverage Memory

The framework **remembers what it tested**:
- Tracks which pages and features have coverage
- Identifies untested or stale areas
- Prioritizes gaps in subsequent runs
- Detects regressions automatically

### Natural Language Hints

Guide priorities **without writing test specs**:

```json
{
  "hints": [
    "The checkout flow is our most critical path",
    "We recently redesigned the pricing page",
    "The search feature has been buggy with special characters"
  ]
}
```

The AI interprets these hints and adjusts test generation accordingly.

### Works Without AI (Gracefully)

No API key? No problem:
- Still crawls and executes tests
- Uses template-based test generation
- Skips AI summaries and fallback recovery
- All core functionality remains available

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ai-qa-framework
cd ai-qa-framework

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Set up your API key (optional but recommended)
export ANTHROPIC_API_KEY=your_key_here
```

### First Run

```bash
# Create a config file for your site
python -m src.cli init --target https://yoursite.com

# Run the full pipeline
python -m src.cli run

# View your report
open qa-reports/report_*.html
```

That's it! The framework will:
- Crawl your site (5-10 minutes for ~50 pages)
- Generate tests (30-60 seconds)
- Execute tests (10-20 minutes for ~25 tests)
- Create a detailed HTML report

---

## Configuration

### Minimal Setup

The bare minimum in `qa-config.json`:

```json
{
  "target_url": "https://yoursite.com"
}
```

### Typical Setup

```json
{
  "target_url": "https://yoursite.com",

  "categories": ["functional", "visual", "security"],

  "auth": {
    "login_url": "https://yoursite.com/login",
    "username": "testuser@example.com",
    "password": "env:QA_TEST_PASSWORD"
  },

  "hints": [
    "The checkout flow is critical",
    "Search has been buggy lately"
  ],

  "max_tests_per_run": 100,
  "max_execution_time_seconds": 1800
}
```

**See [REQUIREMENTS.md](./REQUIREMENTS.md)** for complete configuration options.

---

## CLI Commands

### Pipeline Operations

```bash
# Full pipeline (crawl → plan → execute → report)
python -m src.cli run

# Individual stages
python -m src.cli crawl                    # Discover site structure
python -m src.cli plan                     # Generate test plan
python -m src.cli execute --plan-file ...  # Run specific tests
```

### Coverage Management

```bash
# View coverage statistics
python -m src.cli coverage

# Find coverage gaps
python -m src.cli coverage --gaps

# Reset coverage history
python -m src.cli coverage --reset
```

### Hint Management

```bash
# Add a priority hint
python -m src.cli hint add "Prioritize the checkout flow"

# List current hints
python -m src.cli hint list

# Clear all hints
python -m src.cli hint clear
```

**See [REQUIREMENTS.md](./REQUIREMENTS.md)** for detailed CLI documentation.

---

## Real-World Example

Let's say you're testing an e-commerce site. Here's what happens:

### 1. Initial Crawl

The framework discovers:
- Homepage, product listings, product details
- Cart, checkout, account pages
- Search, filters, pagination
- Forms (contact, newsletter, checkout)
- API endpoints for product data

### 2. AI Planning

Claude generates tests like:
- "Add product to cart and verify cart count updates"
- "Submit contact form with invalid email and verify error message"
- "Visual baseline: Product detail page on mobile"
- "Security: XSS protection on search field"
- "Navigate from homepage to checkout"

### 3. Smart Execution

During testing:
- A button selector changed? AI analyzes the screenshot and finds the new selector
- An unexpected modal appeared? AI decides whether to close it or fail the test
- All steps are captured with screenshots for debugging

### 4. Insightful Report

The report shows:
- 87% of tests passed
- 2 new regressions found (checkout button, search filters)
- Security finding: XSS payload not sanitized on review form
- Visual regression: Logo alignment shifted 5px
- AI summary: "Payment step is failing due to updated selector. Search has a potential XSS vulnerability."

---

## Project Structure

```
ai-qa-framework/
├── src/
│   ├── crawler/          # Site discovery engine
│   ├── planner/          # AI test generation
│   ├── executor/         # Test runner with fallback
│   ├── reporter/         # Report generation
│   ├── coverage/         # Coverage tracking
│   ├── ai/               # Claude API integration
│   └── models/           # Data structures
│
├── qa-config.json        # Your configuration
├── .qa-framework/        # Generated data
│   ├── site_model/       # Crawl results
│   ├── coverage/         # Coverage registry
│   └── debug/            # AI debug logs
│
└── qa-reports/           # Test reports (HTML/JSON)
```

---

## Who Is This For?

### Development Teams

- **Save time**: No test script maintenance
- **Increase coverage**: AI finds edge cases you might miss
- **Catch regressions**: Automated visual and functional checks
- **Test continuously**: Run on every deploy

### QA Engineers

- **Focus on strategy**: Let AI handle test generation
- **Faster onboarding**: New sites test-ready in minutes
- **Better insights**: AI-powered analysis of failures

### Solo Developers

- **QA without a team**: Get enterprise-level testing alone
- **Sleep better**: Know your site is thoroughly tested
- **Ship faster**: Automated testing = confident deploys

---

## Limitations & Considerations

### Current Limitations

- **Browser support**: Chromium only (Firefox/WebKit coming)
- **Authentication**: Simple form-based only (no OAuth/SAML)
- **Same-origin only**: Doesn't follow cross-domain links
- **AI required for best results**: Basic fallback mode available without API key

### Best Suited For

- Web applications with forms and workflows
- Sites that change frequently
- Teams that want comprehensive coverage without manual effort
- Projects where regression detection is critical

### Not Ideal For

- Sites with heavy authentication requirements (OAuth, MFA)
- Applications with complex real-time interactions
- Systems requiring distributed load testing
- Projects where deterministic tests are required by compliance

**See [REQUIREMENTS.md](./REQUIREMENTS.md)** for technical specifications and limitations.

---

## How It Compares

| Feature | Manual Testing | Selenium/Playwright Scripts | AI QA Framework |
|---------|---------------|---------------------------|-----------------|
| **Setup time** | N/A | Days/weeks | Minutes |
| **Test authoring** | Manual | Manual scripting | Automatic |
| **Selector maintenance** | Manual | Manual updates | AI-assisted |
| **Coverage decisions** | Manual | Manual | AI-driven |
| **Failure analysis** | Manual debugging | Script debugging | AI analysis |
| **Adaptation** | Re-test manually | Rewrite scripts | Self-healing |
| **New feature coverage** | Manual discovery | Manual scripting | Automatic |

---

## Technical Stack

- **Python 3.12+** for framework core
- **Playwright** for browser automation
- **Claude AI (Anthropic)** for intelligent test generation
- **Pydantic** for data validation
- **Jinja2** for report templating
- **Pillow** for image comparison

---

## Documentation

### Quick References

- **[README.md](./README.md)** - Quick start and basic usage
- **[OVERVIEW.md](./OVERVIEW.md)** - This document (you are here)
- **[REQUIREMENTS.md](./REQUIREMENTS.md)** - Complete technical specification
- **[OriginalSpec.md](./OriginalSpec.md)** - Original design document

### Detailed Documentation

For developers and advanced users:

- **[Architecture & Components](./REQUIREMENTS.md#core-architecture)** - System design
- **[Configuration Options](./REQUIREMENTS.md#configuration)** - All settings explained
- **[Test Types & Assertions](./REQUIREMENTS.md#test-types--assertions)** - What can be tested
- **[Coverage System](./REQUIREMENTS.md#reporting--coverage)** - How coverage tracking works
- **[AI Integration](./REQUIREMENTS.md#ai-integration)** - How AI is used
- **[Extending the Framework](./REQUIREMENTS.md#extensibility)** - Adding custom features

---

## Getting Help

### Resources

- **GitHub Issues**: Report bugs or request features
- **Documentation**: See [REQUIREMENTS.md](./REQUIREMENTS.md) for detailed specs
- **Examples**: Check `qa-config.json` for configuration examples

### Common Questions

**Q: Do I need an API key?**
A: No, but strongly recommended. Without it, you get basic test generation instead of AI-powered tests.

**Q: How much does it cost?**
A: The framework is free. Claude API usage costs ~$0.50-2.00 per full run depending on site size.

**Q: Can it test authenticated areas?**
A: Yes, with simple form-based login. OAuth/SAML support planned.

**Q: Will it break my site?**
A: No. All actions are read-only except form submissions (which you can control).

**Q: How long does it take?**
A: Typical full run: 20-30 minutes for a 50-page site with 25 tests.

---

## Contributing

We welcome contributions! Areas of interest:

- Additional test categories (accessibility, performance)
- Multi-browser support (Firefox, WebKit)
- Enhanced authentication (OAuth, SAML)
- Distributed execution
- Custom assertion types

**See [REQUIREMENTS.md](./REQUIREMENTS.md#contributing)** for contribution guidelines.

---

## License

[Insert License Information]

---

## What's Next?

Ready to get started?

```bash
# Install and run your first test
pip install -r requirements.txt
playwright install chromium
python -m src.cli init --target https://yoursite.com
export ANTHROPIC_API_KEY=your_key_here
python -m src.cli run
```

**Happy testing!**
