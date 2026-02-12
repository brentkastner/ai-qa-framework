# AI QA Framework

Autonomous AI-driven website QA framework. Provide a URL — the system crawls, plans, tests, and reports automatically.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Initialize config for your site
python -m src.cli init --target https://yoursite.com

# Run the full pipeline
export ANTHROPIC_API_KEY=your_key_here
python -m src.cli run

# Or run stages individually
python -m src.cli crawl
python -m src.cli plan
python -m src.cli execute --plan-file .qa-framework/latest_plan.json
```

## How It Works

1. **Crawl** — Discovers pages, forms, interactive elements, and API endpoints using a real browser (Playwright).
2. **Plan** — AI (Claude) analyzes the site model and generates a structured test plan covering functional, visual, and security tests.
3. **Execute** — Runs tests via Playwright with AI-assisted fallback when elements can't be found.
4. **Report** — Produces HTML/JSON reports with screenshots, AI-generated summaries, and regression detection.

## Configuration

Edit `qa-config.json`:

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
    "The checkout flow is our most critical path",
    "We recently redesigned the pricing page"
  ]
}
```

### Hints

Hints are optional natural-language strings that guide the AI planner's priorities without writing test specs:

```bash
qa-framework hint add "The search feature has been buggy with special characters"
qa-framework hint list
qa-framework hint clear
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python -m src.cli run` | Full pipeline: crawl → plan → execute → report |
| `python -m src.cli crawl` | Discover site structure |
| `python -m src.cli plan` | Generate test plan (requires prior crawl) |
| `python -m src.cli execute --plan-file <path>` | Execute a saved plan |
| `python -m src.cli coverage` | View coverage summary |
| `python -m src.cli coverage --gaps` | View coverage gaps |
| `python -m src.cli coverage --reset` | Reset coverage data |
| `python -m src.cli init --target <url>` | Create default config |
| `python -m src.cli hint add/list/clear` | Manage AI hints |

## Project Structure

```
src/
  cli.py              # CLI entry point
  orchestrator.py     # Pipeline coordinator
  crawler/            # Site discovery (Playwright-based)
  planner/            # AI test plan generation (Claude API)
  executor/           # Test execution engine
  coverage/           # Coverage tracking & gap analysis
  reporter/           # HTML/JSON report generation
  ai/                 # Claude API client & prompts
  models/             # Pydantic data models
```

## Environment Variables

- `ANTHROPIC_API_KEY` — Required for AI-powered planning, fallback, and summaries. Framework works in fallback mode without it.
- `QA_TEST_PASSWORD` — Example: passwords in config use `env:VARIABLE_NAME` syntax.

## Requirements

- Python 3.12+
- Chromium (installed via `playwright install chromium`)
- Anthropic API key (optional but recommended)
- Dependencies listed in `requirements.txt`
