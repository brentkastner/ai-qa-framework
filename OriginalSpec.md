# AI QA Framework — Requirements Document

**Project:** Autonomous AI-Driven Website QA Framework
**Version:** 1.0 Draft
**Date:** February 11, 2026

---

## 1. Executive Summary

This document defines the requirements for an autonomous QA framework that uses AI to discover, test, and report on any website without manual test authoring. **The user provides only a target URL and optional configuration — the system autonomously crawls the site, decides what to test, generates test cases, executes them, and reports results.** No test scripts, selectors, or assertions are written by hand. The user may optionally provide natural-language "hints" (e.g., `"The checkout flow is critical"`) to influence prioritization, but the system works fully autonomously without them.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Runtime target | SPAs + server-rendered sites | Full browser automation covers all site types |
| Test categories (v1) | Functional, Visual/Layout, Security Surface | Core value with broad coverage |
| Language/stack | Python + Playwright | Strong AI ecosystem + native async browser automation |
| AI integration model | Hybrid (AI plans, deterministic executor, AI fallback) | Cost-efficient with robustness for edge cases |
| LLM provider | Claude API (Anthropic) | Primary AI engine for planning and analysis |
| Persistence | JSON files | Simple, inspectable, version-controllable |

---

## 2. System Architecture

### 2.1 High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR (CLI / API)                     │
│  Accepts config → Runs pipeline → Outputs reports                   │
└──────┬──────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
│   CRAWLER    │───▶│   PLANNER    │───▶│   EXECUTOR   │───▶│  REPORTER   │
│  (Discovery) │    │ (AI: Claude) │    │ (Playwright) │    │ (AI + Data) │
└──────────────┘    └──────────────┘    └──────┬───────┘    └─────────────┘
       │                    ▲                   │                   │
       ▼                    │                   ▼                   ▼
┌──────────────┐    ┌───────┴──────┐    ┌──────────────┐    ┌─────────────┐
│  SITE MODEL  │    │   COVERAGE   │    │   AI FALLBACK│    │   REPORTS   │
│  (JSON)      │    │   REGISTRY   │    │   (Claude)   │    │  (HTML/JSON)│
│              │    │   (JSON)     │    │              │    │             │
└──────────────┘    └──────────────┘    └──────────────┘    └─────────────┘
```

### 2.2 Component Overview

| Component | Responsibility | Inputs | Outputs |
|-----------|---------------|--------|---------|
| **Crawler** | Discover site structure, pages, elements, flows | Target URL + config | Site Model (JSON) |
| **Planner** | Generate structured test plans using AI | Site Model + Coverage Registry | Test Plan (JSON) |
| **Executor** | Run tests via Playwright, capture evidence | Test Plan | Test Results (JSON) + artifacts |
| **AI Fallback** | Handle unexpected states during execution | Screenshot + DOM + context | Adapted action or skip decision |
| **Reporter** | Summarize results, detect regressions, score coverage | Test Results + Coverage Registry | Reports (HTML/JSON) |
| **Coverage Registry** | Track what has been tested over time | Test Results (per run) | Coverage state + gap analysis |
| **Orchestrator** | Coordinate pipeline, manage config, entry point | CLI args / API call | Full pipeline execution |

---

## 3. Component Specifications

### 3.1 Crawler (Site Discovery)

The crawler builds a comprehensive model of the target site using a real browser context (Playwright) to handle SPAs.

#### 3.1.1 Capabilities

- **Page discovery:** Follow links, detect routes, build a sitemap. Handle hash-based and history-based SPA routing.
- **Element inventory:** For each page, catalog interactive elements — forms, buttons, links, dropdowns, modals, tabs, accordions, toggleable components.
- **Form analysis:** Identify form fields, their types (text, email, password, select, checkbox, file upload), validation patterns, required/optional status.
- **Authentication detection:** Recognize login/signup pages, OAuth flows, session-based auth. Support for provided credentials to test authenticated states.
- **Page type classification:** Categorize pages as listing, detail, form, dashboard, static content, error page, etc.
- **Navigation structure:** Build a graph of page-to-page transitions including navigation menus, breadcrumbs, and in-page links.
- **API endpoint observation:** Intercept and log network requests (XHR/fetch) to identify API endpoints, request methods, and response patterns.
- **State detection:** Identify elements or content that change based on user actions (e.g., cart count, notification badges, toggled states).

#### 3.1.2 Crawl Configuration

```python
@dataclass
class CrawlConfig:
    target_url: str                    # Starting URL
    max_pages: int = 50                # Page limit to prevent runaway crawls
    max_depth: int = 5                 # Link-follow depth
    include_patterns: list[str] = []   # Regex patterns for URLs to include
    exclude_patterns: list[str] = []   # Regex patterns for URLs to exclude
    auth_credentials: dict | None = None  # {"username": "...", "password": "..."}
    auth_url: str | None = None        # Login page URL
    wait_for_idle: bool = True         # Wait for network idle before cataloging
    viewport: dict = {"width": 1280, "height": 720}
    user_agent: str | None = None      # Custom UA string
```

#### 3.1.3 Site Model Output

```python
@dataclass
class SiteModel:
    base_url: str
    pages: list[PageModel]
    navigation_graph: dict[str, list[str]]  # page_id -> [linked_page_ids]
    api_endpoints: list[APIEndpoint]
    auth_flow: AuthFlow | None
    crawl_metadata: dict  # timestamp, duration, pages_found, etc.

@dataclass
class PageModel:
    page_id: str              # Stable hash based on route + page type
    url: str
    page_type: str            # "listing", "detail", "form", "dashboard", "static", "error"
    title: str
    elements: list[ElementModel]
    forms: list[FormModel]
    network_requests: list[NetworkRequest]
    screenshot_path: str      # Baseline screenshot
    dom_snapshot_path: str    # Serialized DOM for comparison

@dataclass
class ElementModel:
    element_id: str
    tag: str
    selector: str             # CSS selector (preferred) or XPath
    role: str                 # ARIA role or inferred role
    text_content: str
    is_interactive: bool
    element_type: str         # "button", "link", "input", "dropdown", etc.
    attributes: dict

@dataclass
class FormModel:
    form_id: str
    action: str
    method: str
    fields: list[FormField]
    submit_selector: str

@dataclass
class FormField:
    name: str
    field_type: str           # "text", "email", "password", "select", "checkbox", etc.
    required: bool
    validation_pattern: str | None
    options: list[str] | None  # For select/radio fields
    selector: str
```

### 3.2 Planner (AI Test Generation)

The Planner uses the Claude API to analyze the Site Model and Coverage Registry and produce a structured Test Plan. **The Planner is fully autonomous — it decides what to test, how to test it, and what to assert, with no manual test authoring required.** The user provides only a target URL and optional configuration; the AI does the rest.

#### 3.2.1 Planning Process

1. **Load context:** Read the Site Model and the current Coverage Registry.
2. **Incorporate hints:** If the user has provided natural-language hints (see 3.2.6), feed them to the AI to influence prioritization and focus.
3. **Identify coverage gaps:** Determine which pages, elements, and test categories are under-tested or never tested.
4. **Risk assessment:** Prioritize testing areas based on complexity, criticality (forms > static pages), recency of last test, and user hints.
5. **Generate test plan:** Produce a structured JSON test plan with individual test cases.
6. **Budget awareness:** Respect the configured max execution time and max test count.

#### 3.2.2 AI Prompt Strategy

The Planner sends the Claude API a structured prompt containing:
- The full Site Model (or a summarized version for large sites)
- The Coverage Registry summary (what's been tested, when, results)
- The test configuration (enabled categories, risk preferences, budget)
- A system prompt defining the test plan JSON schema and test generation guidelines

The AI returns a structured test plan conforming to the schema below.

#### 3.2.3 Test Plan Schema

```python
@dataclass
class TestPlan:
    plan_id: str                # Unique ID for this plan
    generated_at: str           # ISO timestamp
    target_url: str
    test_cases: list[TestCase]
    estimated_duration_seconds: int
    coverage_intent: dict       # What gaps this plan aims to fill

@dataclass
class TestCase:
    test_id: str
    name: str                   # Human-readable name
    description: str            # What this test verifies
    category: str               # "functional", "visual", "security"
    priority: int               # 1 (critical) to 5 (low)
    target_page_id: str         # Which page this tests
    coverage_signature: str     # Abstract description for registry matching
    preconditions: list[Action] # Steps to reach the right state
    steps: list[Action]         # The actual test actions
    assertions: list[Assertion] # What to verify
    timeout_seconds: int = 30

@dataclass
class Action:
    action_type: str            # "navigate", "click", "fill", "select", "hover",
                                # "scroll", "wait", "screenshot", "keyboard"
    selector: str | None        # Target element
    value: str | None           # Input value (for fill, select)
    description: str            # Human-readable step description

@dataclass
class Assertion:
    assertion_type: str         # "element_visible", "element_hidden", "text_contains",
                                # "text_equals", "url_matches", "screenshot_diff",
                                # "element_count", "network_request_made",
                                # "no_console_errors", "response_status"
    selector: str | None
    expected_value: str | None
    tolerance: float | None     # For visual diff (0.0 = exact, 1.0 = any)
    description: str
```

#### 3.2.4 Test Category Specifications

**Functional Tests:**
- Form submission with valid data (happy path)
- Form submission with invalid data (validation errors)
- Navigation links resolve correctly
- CRUD operations complete successfully
- Search/filter functionality returns expected results
- Pagination works correctly
- Modal/dialog open and close behavior
- Multi-step workflow completion (e.g., checkout, onboarding)
- Session/auth state transitions

**Visual/Layout Tests:**
- Screenshot comparison against baseline (pixel diff with tolerance)
- Element visibility at expected viewport sizes
- Responsive breakpoint verification (mobile, tablet, desktop)
- No overlapping elements
- Text readability (no truncation, overflow)
- Image loading verification
- Consistent spacing and alignment checks

**Security Surface Tests:**
- XSS probe: inject common payloads into form fields, verify they are sanitized
- Open redirect: test URL parameters for redirect manipulation
- Sensitive data exposure: check DOM and network responses for tokens, passwords, PII patterns
- HTTPS enforcement: verify redirects from HTTP to HTTPS
- Cookie security: check for HttpOnly, Secure, SameSite attributes
- Clickjacking: verify X-Frame-Options or CSP frame-ancestors headers
- Form action integrity: verify forms submit to expected domains
- Error page information leakage: check that error pages don't expose stack traces or internal paths

#### 3.2.6 User Hints (Optional)

Hints are optional natural-language strings provided by the user in the configuration. They allow the user to influence the AI Planner's priorities **without writing any test definitions.** The system is fully autonomous without hints — they simply sharpen its focus.

**How hints are used:**

1. Hints are injected into the Planner's Claude API prompt alongside the Site Model and Coverage Registry.
2. The AI interprets them as prioritization signals, not as test specifications.
3. A hint like `"The checkout flow is our most critical path"` causes the Planner to:
   - Allocate more of the test budget to checkout-related pages
   - Generate more edge-case and negative tests for those pages
   - Assign higher priority values to those test cases
   - Increase visual regression sensitivity for those pages
4. A hint like `"We recently redesigned the pricing page"` causes the Planner to:
   - Lower the visual diff tolerance for that page (stricter comparison)
   - Regenerate the visual baseline if the diff exceeds a threshold
   - Test responsive behavior more thoroughly on that page

**Hint guidelines (communicated to the user via `qa-framework init` and docs):**

- Hints should describe *what matters*, not *how to test it*. Good: `"The search feature has been buggy with special characters"`. Bad: `"Click the search box, type <script>, and check for XSS"`.
- Hints can reference specific pages, features, or general concerns.
- There is no limit on the number of hints, but 3–10 is the practical sweet spot. Too many hints dilute their prioritization effect.
- Hints persist across runs (they're in the config file), so the user can update them as their concerns evolve.

**Hint schema in config:**

```python
# In FrameworkConfig
hints: list[str] = []  # Optional, natural-language guidance for AI Planner
```

**Prompt integration example:**

```
You are generating a test plan for {target_url}.

[Site Model summary...]
[Coverage Registry gaps...]

The user has provided the following guidance about their priorities:
- "The checkout flow is our most critical user path"
- "The search feature has been buggy lately, especially with special characters"

Use these hints to influence your prioritization. Allocate more test budget
and generate more thorough tests for the areas the user has flagged.
These are guidance signals, not test specifications — you still decide
what specific tests to generate.
```

### 3.3 Executor (Test Runner)

The Executor is a deterministic state machine that translates the structured Test Plan into Playwright browser actions.

#### 3.3.1 Execution Flow

```
For each TestCase in priority order:
  1. Execute preconditions (navigate to page, log in, etc.)
  2. For each step:
     a. Translate Action to Playwright call
     b. Execute with configured timeout
     c. If element not found or unexpected state:
        → Capture screenshot + DOM + console logs
        → Call AI Fallback for guidance
        → AI returns: retry with new selector | skip step | abort test
     d. Capture step evidence (screenshot, network log)
  3. Evaluate assertions
  4. Record result (pass/fail/skip/error) with evidence
  5. Update Coverage Registry
```

#### 3.3.2 Action Translation Map

| Action Type | Playwright Call |
|------------|----------------|
| `navigate` | `page.goto(url)` |
| `click` | `page.click(selector)` |
| `fill` | `page.fill(selector, value)` |
| `select` | `page.select_option(selector, value)` |
| `hover` | `page.hover(selector)` |
| `scroll` | `page.evaluate("window.scrollTo(...)")` |
| `wait` | `page.wait_for_selector(selector)` or `page.wait_for_timeout(ms)` |
| `screenshot` | `page.screenshot(path=...)` |
| `keyboard` | `page.keyboard.press(key)` |

#### 3.3.3 Evidence Collection

For every test case, the executor captures:
- **Screenshots:** Before first step, after each significant step, on failure
- **Console logs:** All browser console output during the test
- **Network log:** All HTTP requests/responses (method, URL, status, timing)
- **DOM snapshots:** On failure or for visual comparison
- **Video (optional):** Full test execution recording via Playwright's video support

Evidence is stored in a structured directory:

```
runs/
  {run_id}/
    evidence/
      {test_id}/
        screenshot_step_0.png
        screenshot_step_1.png
        screenshot_failure.png
        console.log
        network.json
        dom_snapshot.html
        video.webm (optional)
```

#### 3.3.4 AI Fallback Protocol

When the executor encounters an unexpected state, it invokes the Claude API with:

```python
@dataclass
class FallbackRequest:
    test_context: str          # What test is running, what step failed
    screenshot_base64: str     # Current page screenshot
    dom_snippet: str           # Relevant portion of the DOM
    console_errors: list[str]  # Recent console errors
    original_action: Action    # What was attempted
    original_selector: str     # What couldn't be found
```

The AI responds with one of:

```python
@dataclass
class FallbackResponse:
    decision: str              # "retry", "skip", "abort", "adapt"
    new_selector: str | None   # If retry, the corrected selector
    new_action: Action | None  # If adapt, a completely different action
    reasoning: str             # Why this decision was made
```

**Fallback budget:** Each test case gets a maximum of 3 AI fallback calls to prevent runaway costs. If all 3 are exhausted without resolution, the test is marked as `error` with full context.

#### 3.3.5 Parallel Execution

- Tests are grouped by `target_page_id` to minimize navigation overhead.
- Independent page groups can run in parallel browser contexts.
- Tests within a group that share preconditions are batched.
- Configurable concurrency: `max_parallel_contexts` (default: 3).

### 3.4 Coverage Registry

The Coverage Registry is the system's "memory" — it ensures consistent coverage across non-deterministic test runs.

#### 3.4.1 Data Model

```python
@dataclass
class CoverageRegistry:
    target_url: str
    last_updated: str
    pages: dict[str, PageCoverage]       # page_id -> coverage
    journeys: dict[str, JourneyCoverage] # journey_id -> coverage
    global_stats: GlobalCoverageStats

@dataclass
class PageCoverage:
    page_id: str
    url: str
    page_type: str
    categories: dict[str, CategoryCoverage]  # "functional" -> coverage
    elements_tested: dict[str, ElementCoverage]
    last_tested: str          # ISO timestamp
    test_count: int           # How many times this page has been tested

@dataclass
class CategoryCoverage:
    category: str
    signatures_tested: list[SignatureRecord]
    coverage_score: float     # 0.0 to 1.0
    last_tested: str

@dataclass
class SignatureRecord:
    signature: str            # e.g., "submit_contact_form_valid_data"
    last_tested: str
    last_result: str          # "pass", "fail", "skip", "error"
    test_count: int
    history: list[TestResultSummary]  # Last N results

@dataclass
class TestResultSummary:
    run_id: str
    timestamp: str
    result: str
    duration_seconds: float
    failure_reason: str | None

@dataclass
class GlobalCoverageStats:
    total_pages: int
    pages_tested: int
    overall_score: float
    category_scores: dict[str, float]
    last_full_run: str
    regression_count: int     # Tests that went from pass to fail
```

#### 3.4.2 Coverage Score Calculation

Coverage score per page per category is calculated as:

```
score = (unique_signatures_tested / estimated_total_signatures) × recency_weight
```

Where:
- `unique_signatures_tested` = number of distinct test signatures with at least one pass in the last N runs
- `estimated_total_signatures` = AI's estimate of how many distinct tests this page/category warrants (stored during planning)
- `recency_weight` = decays from 1.0 to 0.5 over configurable staleness period (default: 7 days)

#### 3.4.3 Gap Analysis

Before each planning phase, the registry produces a gap report:

```python
@dataclass
class CoverageGapReport:
    untested_pages: list[str]                    # Never tested
    stale_pages: list[str]                       # Tested but stale
    low_coverage_areas: list[tuple[str, str, float]]  # (page_id, category, score)
    recent_failures: list[tuple[str, str]]       # (page_id, signature) that failed recently
    suggested_focus: list[str]                   # AI's prioritized list of what to test next
```

#### 3.4.4 File Structure

```
.qa-framework/
  coverage/
    registry.json              # Main coverage state
    history/
      {run_id}.json            # Per-run results snapshot
  site_model/
    model.json                 # Latest crawl result
    baselines/
      {page_id}_screenshot.png # Visual baselines
  config.json                  # Framework configuration
```

### 3.5 Reporter

The Reporter generates human-readable and machine-readable output from test results.

#### 3.5.1 Report Types

**Run Report (per execution):**
- Summary: total tests, pass/fail/skip/error counts, duration
- Per-test detail: name, category, result, duration, failure reason, screenshot links
- Regression alerts: tests that passed previously but now fail
- New discoveries: pages or elements found that weren't in previous crawls
- AI confidence notes: where the AI fallback was invoked and what it decided

**Coverage Report (cumulative):**
- Coverage heatmap: pages × categories with color-coded scores
- Trend graph data: coverage scores over time
- Gap analysis: what's untested or stale
- Recommendations: AI-generated suggestions for improving test coverage

**Regression Report (diff between runs):**
- New failures since last run
- Resolved failures (previously failing, now passing)
- New pages discovered
- Pages that disappeared

#### 3.5.2 Output Formats

- **HTML:** Self-contained report with embedded screenshots, expandable sections, styled tables
- **JSON:** Machine-readable for CI/CD integration
- **Markdown:** For easy inclusion in repos or documentation
- **Console:** Summary output for CLI usage

#### 3.5.3 AI-Generated Summary

After each run, the Reporter sends results to Claude for a natural-language summary:

```
"Tested 34 pages across 3 categories. 89 tests passed, 4 failed, 2 were skipped.
Key findings:
- The checkout flow fails at the payment step — the submit button selector has changed.
- Two forms on the contact page lack CSRF tokens.
- Visual regression detected on the homepage: the hero banner image is no longer loading.
Coverage improved from 72% to 78% since last run. Remaining gaps are primarily
in the admin dashboard (untested) and mobile responsive behavior."
```

---

## 4. Configuration

### 4.1 Framework Configuration

```python
@dataclass
class FrameworkConfig:
    # Target
    target_url: str
    
    # Authentication
    auth: AuthConfig | None = None
    
    # Crawl settings
    crawl: CrawlConfig = CrawlConfig()
    
    # Test categories
    categories: list[str] = ["functional", "visual", "security"]
    
    # Execution limits
    max_tests_per_run: int = 100
    max_execution_time_seconds: int = 1800  # 30 minutes
    max_parallel_contexts: int = 3
    
    # AI settings
    ai_model: str = "claude-opus-4-6"
    ai_max_fallback_calls_per_test: int = 3
    ai_max_planning_tokens: int = 8000
    
    # Coverage settings
    staleness_threshold_days: int = 7
    history_retention_runs: int = 20
    
    # Visual testing
    visual_diff_tolerance: float = 0.05   # 5% pixel diff threshold
    viewports: list[dict] = [
        {"width": 1280, "height": 720, "name": "desktop"},
        {"width": 768, "height": 1024, "name": "tablet"},
        {"width": 375, "height": 812, "name": "mobile"}
    ]
    
    # Security testing
    security_xss_payloads: list[str] = [...]  # Built-in payload list
    security_max_probe_depth: int = 2
    
    # Reporting
    report_formats: list[str] = ["html", "json"]
    report_output_dir: str = "./qa-reports"
    capture_video: bool = False
    
    # Scope
    include_url_patterns: list[str] = []
    exclude_url_patterns: list[str] = []
    
    # Hints (optional, natural-language guidance for the AI Planner)
    hints: list[str] = []

@dataclass
class AuthConfig:
    login_url: str
    username: str
    password: str
    username_selector: str = "input[name='username'], input[type='email']"
    password_selector: str = "input[name='password'], input[type='password']"
    submit_selector: str = "button[type='submit']"
    success_indicator: str = ""  # Selector or URL pattern that confirms login success
```

### 4.2 Configuration File

The framework reads from `qa-config.json` at the project root:

```json
{
  "target_url": "https://example.com",
  "categories": ["functional", "visual", "security"],
  "auth": {
    "login_url": "https://example.com/login",
    "username": "testuser@example.com",
    "password": "env:QA_TEST_PASSWORD"
  },
  "crawl": {
    "max_pages": 50,
    "max_depth": 5,
    "exclude_patterns": ["/admin/.*", "/api/.*"]
  },
  "max_tests_per_run": 100,
  "max_execution_time_seconds": 1800,
  "viewports": [
    {"width": 1280, "height": 720, "name": "desktop"},
    {"width": 375, "height": 812, "name": "mobile"}
  ],
  "report_formats": ["html", "json"],

  "hints": [
    "The checkout flow is our most critical user path",
    "We recently redesigned the pricing page — watch for visual regressions",
    "The search feature has been buggy lately, especially with special characters",
    "The /settings page has a file upload that has caused issues"
  ]
}
```

---

## 5. CLI Interface

```bash
# Full pipeline: crawl → plan → execute → report
qa-framework run --config qa-config.json

# Individual stages
qa-framework crawl --config qa-config.json          # Only crawl, output site model
qa-framework plan --config qa-config.json            # Only plan (requires existing site model)
qa-framework execute --plan plan.json                # Only execute a saved plan
qa-framework report --run-id <run_id>                # Regenerate report for a past run

# Coverage management
qa-framework coverage                                # Show current coverage summary
qa-framework coverage --gaps                         # Show coverage gaps
qa-framework coverage --reset                        # Reset coverage registry

# Utilities
qa-framework init                                    # Create default config file
qa-framework baseline --page <url>                   # Capture visual baseline for a page
qa-framework hint add "The checkout flow is critical" # Add a hint without editing config
qa-framework hint list                               # Show current hints
qa-framework hint clear                              # Remove all hints
```

---

## 6. Error Handling & Resilience

### 6.1 Graceful Degradation

| Failure Scenario | Behavior |
|-----------------|----------|
| Page fails to load | Skip all tests for that page, log error, continue |
| Element not found | Invoke AI Fallback (up to 3 attempts), then skip test |
| AI API unavailable | Fall back to executing tests without adaptation; skip planning if no cached plan |
| AI returns invalid test plan | Validate against schema, reject invalid tests, log warning |
| Browser crash | Restart browser context, retry current test, continue |
| Timeout exceeded | Stop new tests, complete current test, generate partial report |
| Network error during crawl | Retry page 2x, then skip and note in site model |

### 6.2 Logging

All components log to both console and file:
- `DEBUG`: Full Playwright actions, AI prompts/responses
- `INFO`: Test execution progress, results, coverage updates
- `WARNING`: Fallback invocations, retries, skipped tests
- `ERROR`: Failures, crashes, unrecoverable issues

Log output: `runs/{run_id}/framework.log`

---

## 7. Project Structure

```
ai-qa-framework/
├── pyproject.toml                # Project metadata, dependencies
├── README.md
├── qa-config.json                # Default configuration
│
├── src/
│   ├── __init__.py
│   ├── cli.py                    # CLI entry point (click or argparse)
│   ├── orchestrator.py           # Pipeline coordinator
│   │
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── crawler.py            # Main crawl logic
│   │   ├── element_extractor.py  # DOM element cataloging
│   │   ├── form_analyzer.py      # Form field detection
│   │   └── spa_handler.py        # SPA-specific routing detection
│   │
│   ├── planner/
│   │   ├── __init__.py
│   │   ├── planner.py            # Test plan generation orchestration
│   │   ├── prompts.py            # Claude API prompt templates
│   │   └── schema_validator.py   # Test plan JSON schema validation
│   │
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── executor.py           # Main test execution engine
│   │   ├── action_runner.py      # Action -> Playwright translation
│   │   ├── assertion_checker.py  # Assertion evaluation
│   │   ├── evidence_collector.py # Screenshot, network, console capture
│   │   └── fallback.py           # AI fallback handler
│   │
│   ├── coverage/
│   │   ├── __init__.py
│   │   ├── registry.py           # Coverage registry CRUD
│   │   ├── gap_analyzer.py       # Coverage gap detection
│   │   └── scorer.py             # Coverage score calculation
│   │
│   ├── reporter/
│   │   ├── __init__.py
│   │   ├── reporter.py           # Report generation orchestration
│   │   ├── html_report.py        # HTML report template
│   │   ├── json_report.py        # JSON report output
│   │   └── regression_detector.py # Diff between runs
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── client.py             # Claude API client wrapper
│   │   └── prompts/
│   │       ├── planning.py       # System prompts for test planning
│   │       ├── fallback.py       # System prompts for fallback decisions
│   │       └── summary.py        # System prompts for report summarization
│   │
│   └── models/
│       ├── __init__.py
│       ├── site_model.py         # SiteModel, PageModel, etc.
│       ├── test_plan.py          # TestPlan, TestCase, Action, Assertion
│       ├── test_result.py        # TestResult, Evidence
│       ├── coverage.py           # CoverageRegistry, PageCoverage, etc.
│       └── config.py             # FrameworkConfig, CrawlConfig, etc.
│
├── tests/                        # Framework's own unit/integration tests
│   ├── test_crawler.py
│   ├── test_planner.py
│   ├── test_executor.py
│   ├── test_coverage.py
│   └── test_reporter.py
│
└── templates/
    └── report.html               # Jinja2 HTML report template
```

---

## 8. Dependencies

### Core

| Package | Purpose |
|---------|---------|
| `playwright` | Browser automation (Chromium, Firefox, WebKit) |
| `anthropic` | Claude API client |
| `pydantic` | Data models and validation |
| `click` | CLI framework |
| `jinja2` | HTML report templating |
| `Pillow` | Image comparison for visual diffs |
| `aiofiles` | Async file I/O for evidence collection |

### Optional

| Package | Purpose |
|---------|---------|
| `pixelmatch` | Precise pixel-level image comparison |
| `rich` | Enhanced console output and progress bars |
| `uvloop` | Faster async event loop |

---

## 9. Security & Privacy Considerations

- **Credentials:** Auth passwords support `env:VARIABLE_NAME` syntax to avoid plaintext storage.
- **API keys:** Claude API key is read from `ANTHROPIC_API_KEY` environment variable, never stored in config.
- **Security tests are non-destructive:** XSS probes use benign payloads (e.g., `<script>alert(1)</script>`) and verify sanitization — they do not attempt actual exploitation.
- **Scope enforcement:** The crawler and executor strictly respect `include_patterns` and `exclude_patterns` to prevent testing outside authorized scope.
- **Evidence sensitivity:** Reports and screenshots may contain sensitive data. The `report_output_dir` should be treated accordingly.

---

## 10. Future Enhancements (v2+)

These are explicitly out of scope for v1 but inform the architecture:

- **Accessibility (a11y) testing category** — WCAG compliance checks, keyboard navigation, ARIA validation
- **Performance testing category** — Core Web Vitals, load time profiling
- **CI/CD integration** — GitHub Actions / GitLab CI templates, webhook triggers
- **Multi-browser testing** — Run across Chromium, Firefox, WebKit simultaneously
- **Distributed execution** — Run tests across multiple machines
- **Self-healing selectors** — AI learns from fallback patterns to preemptively update selectors
- **API-level testing** — Direct API testing based on discovered endpoints
- **Scheduled runs** — Built-in cron-like scheduler
- **Dashboard UI** — Web-based dashboard for viewing coverage and results over time

---

## 11. Acceptance Criteria for v1

The framework is considered complete when:

1. **Crawl:** Given a target URL, it can discover pages and elements for both server-rendered and SPA sites.
2. **Plan:** It generates a valid, schema-conforming test plan with tests across all three categories (functional, visual, security).
3. **Execute:** It runs the plan using Playwright, captures evidence, and invokes AI fallback when needed.
4. **Coverage:** It tracks coverage in a JSON registry and uses it to influence subsequent test plans.
5. **Report:** It produces an HTML report with per-test results, screenshots, and an AI-generated summary.
6. **Gap filling:** On consecutive runs, coverage scores should increase (assuming the site doesn't change) because the planner targets gaps.
7. **Resilience:** Individual test failures don't crash the pipeline; partial results are always available.
8. **CLI:** All operations are accessible via a clean CLI interface.
