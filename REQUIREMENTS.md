# AI QA Framework - Requirements & Features Documentation

> **📚 Looking for a simpler introduction?** Check out [OVERVIEW.md](./OVERVIEW.md) for a friendly, high-level explanation of what this framework does and why. This document contains the complete technical specification for developers.

---

## Table of Contents
- [Overview](#overview)
- [Core Architecture](#core-architecture)
- [Feature Set](#feature-set)
- [AI Integration](#ai-integration)
- [Configuration](#configuration)
- [Test Types & Assertions](#test-types--assertions)
- [Reporting & Coverage](#reporting--coverage)
- [CLI Interface](#cli-interface)
- [Technical Specifications](#technical-specifications)

---

## Overview

### Purpose
An autonomous AI-driven website quality assurance testing framework that automatically discovers pages, generates comprehensive test plans, executes tests with intelligent fallback mechanisms, and produces detailed reports with minimal manual configuration.

### Key Capabilities
- **Automatic Site Discovery**: Crawls websites using real browsers to map structure and identify testable elements
- **AI-Powered Test Generation**: Uses Claude AI to generate contextual, intelligent test plans
- **Intelligent Test Execution**: Runs tests with AI-assisted error recovery and fallback handling
- **Comprehensive Reporting**: Generates HTML and JSON reports with AI-powered summaries
- **Coverage Tracking**: Maintains test coverage registry with gap analysis and regression detection
- **Graceful Degradation**: Operates in fallback mode without AI API access

### Primary Pipeline
```
Crawl → Plan → Execute → Report
   ↓       ↓       ↓        ↓
Site    Test   Test     HTML/JSON
Model   Plan   Results  Reports
```

---

## Core Architecture

### Component Overview

#### 1. Orchestrator (`src/orchestrator.py`)
**Purpose**: Pipeline coordinator and workflow manager

**Responsibilities**:
- Manages full pipeline execution: crawl → plan → execute → report
- Supports running individual pipeline stages independently
- Handles coverage registry updates and persistence
- Coordinates AI client initialization and fallback behavior
- Manages site model and test plan serialization/deserialization
- Enforces execution time limits and test count budgets

**Key Features**:
- Stage-by-stage or full pipeline execution
- Coverage-aware test planning
- Regression detection
- Graceful handling of missing AI credentials

---

#### 2. Crawler (`src/crawler/`)
**Purpose**: Website structure discovery using Playwright browser automation

##### Main Crawler (`crawler.py`)
**Capabilities**:
- Priority queue-based URL discovery and processing
- Real browser-based crawling (handles JavaScript, SPAs)
- Configurable depth and page limits
- URL pattern filtering (include/exclude)
- Page type detection (listing, detail, form, dashboard, static, error)
- Network request capture and API endpoint discovery
- Screenshot and DOM snapshot collection
- Navigation graph construction

**Priority Levels**:
- START (0) - Initial URL
- ORGANIC (10) - Links discovered naturally
- INTERACTIVE (20) - Links from interactive elements
- SITEMAP (50) - Sitemap URLs

**URL Processing**:
- Same-origin validation
- URL normalization for deduplication
- File type filtering (skips PDFs, images, videos, etc.)
- Respects robots.txt conventions

##### Element Extractor (`element_extractor.py`)
**Purpose**: Identifies and catalogs interactive page elements

**Extracts**:
- Buttons, links, inputs, textareas, selects, checkboxes, radios
- Element roles and ARIA attributes
- Text content and labels
- Stable CSS selectors

**Selector Strategy** (in priority order):
1. `data-testid` attributes
2. HTML `id` attributes
3. `name` attributes (for form elements)
4. `aria-label` attributes
5. CSS class selectors (fallback)

##### Form Analyzer (`form_analyzer.py`)
**Purpose**: Analyzes HTML forms for test generation

**Identifies**:
- Form fields with types (text, email, password, number, tel, url, etc.)
- Required fields and validation patterns
- Select options and values
- Form submission endpoints
- Field labels and placeholder text

**Skips**: Hidden fields, submit buttons, disabled fields

##### SPA Handler (`spa_handler.py`)
**Purpose**: Detects and handles Single Page Applications

**Capabilities**:
- Framework detection (React, Vue, Angular, Svelte)
- Routing type identification (hash-based vs. history API)
- Client-side route discovery
- Dynamic content detection

---

#### 3. Planner (`src/planner/`)
**Purpose**: AI-powered test plan generation

##### Test Planner (`planner.py`)
**Capabilities**:
- Analyzes site model structure using Claude AI
- Generates contextually relevant test cases
- Incorporates coverage gaps from registry
- Respects test category budget allocations
- Uses natural language hints for prioritization
- Falls back to basic plan generation without AI

**Input Sources**:
- Site model (pages, forms, elements, endpoints)
- Coverage registry (gaps, stale tests, recent failures)
- Configuration (test limits, categories, viewports)
- User hints (natural language guidance)

**Output**:
- Structured test plan with test cases
- Estimated execution duration
- Coverage intent mapping

##### Schema Validator (`schema_validator.py`)
**Purpose**: Validates AI-generated test plans

**Validates**:
- Test ID uniqueness
- Category validity (functional/visual/security)
- Priority ranges (1-5)
- Required fields in actions and assertions
- Action type validity
- Assertion type validity
- Selector presence where required

**Actions**: Filters out invalid test cases, logs warnings

---

#### 4. Executor (`src/executor/`)
**Purpose**: Test execution engine with Playwright

##### Main Executor (`executor.py`)
**Capabilities**:
- Executes test plans using browser automation
- Groups tests by target page for efficiency
- Enforces maximum execution time limits
- Handles authentication flows
- Manages evidence collection (screenshots, logs, DOM)
- Records step-by-step execution results
- Supports parallel browser contexts (configurable)

**Execution Flow**:
1. Group tests by target page
2. Initialize browser and contexts
3. Authenticate if configured
4. For each test:
   - Run preconditions
   - Execute test steps
   - Evaluate assertions
   - Invoke AI fallback on failures (if available)
   - Collect evidence
5. Generate run result

##### Action Runner (`action_runner.py`)
**Purpose**: Translates test actions to Playwright commands

**Supported Actions**:
- **navigate**: Load URL with configurable wait states
- **click**: Click element by selector
- **fill**: Fill form field with text
- **select**: Select dropdown option
- **hover**: Hover over element
- **scroll**: Scroll page or element into view
- **wait**: Wait for selector or timeout
- **keyboard**: Press keyboard key
- **screenshot**: Handled by evidence collector

**Features**:
- Configurable timeouts per action
- Network idle waiting after navigation
- Element existence verification

##### Assertion Checker (`assertion_checker.py`)
**Purpose**: Evaluates test assertions against page state

**Supported Assertion Types**:

1. **element_visible**: Verifies element is in DOM and visible
   - Uses selector to locate element
   - Waits up to 5 seconds for visibility

2. **element_hidden**: Verifies element is absent or hidden
   - Checks for element absence or hidden state

3. **text_contains**: Page or element contains text
   - Supports regex patterns
   - Case-sensitive matching

4. **text_equals**: Element text exactly matches expected value
   - Exact string comparison

5. **url_matches**: Current URL matches pattern
   - Supports substring and regex matching

6. **screenshot_diff**: Visual regression detection
   - Compares against baseline screenshot
   - Configurable tolerance (default 0.05 = 5%)
   - Per-pixel threshold (40/255 per RGB channel)
   - Automatic page stabilization (network idle + 500ms)
   - Viewport or full-page screenshots
   - First run creates baseline

7. **element_count**: Verifies number of matching elements
   - Counts elements matching selector

8. **network_request_made**: Verifies specific network request occurred
   - Checks URL pattern in captured network log

9. **no_console_errors**: No JavaScript errors in console
   - Checks console log for error-level messages

10. **response_status**: HTTP response status verification
    - Validates expected status codes

**Visual Testing Features**:
- Waits for network idle before screenshots
- Additional 500ms stabilization for fonts/animations
- Pixel comparison with anti-aliasing tolerance
- Baseline management and comparison
- Configurable global and per-assertion tolerance

##### Fallback Handler (`fallback.py`)
**Purpose**: AI-assisted test recovery when steps fail

**Capabilities**:
- Triggered on test step failures
- Analyzes failure context:
  - Screenshot (vision analysis)
  - DOM snippet (structural context)
  - Console errors
  - Original action details
- Provides recovery decisions:
  - **retry**: New selector provided
  - **adapt**: Different action suggested
  - **skip**: Continue without this step
  - **abort**: Unrecoverable failure

**Budget Management**:
- Configurable max calls per test (default 3)
- Prevents infinite retry loops

**Evidence**:
- Records all fallback attempts
- Captures reasoning
- Tracks recovery success/failure

##### Evidence Collector (`evidence_collector.py`)
**Purpose**: Captures test execution evidence

**Collects**:
- Screenshots at key points (initial, per-step, final, on failure)
- Console logs (info, warning, error)
- Network requests (URL, method, status, timing)
- DOM snapshots at failure points

**Features**:
- Configurable evidence limits
- Organized by test run and test ID
- Screenshot naming conventions
- Log persistence to disk

---

#### 5. Reporter (`src/reporter/`)
**Purpose**: Test result reporting and analysis

##### Reporter Orchestrator (`reporter.py`)
**Capabilities**:
- Generates HTML and/or JSON reports
- Creates AI-powered natural language summaries
- Detects regressions vs. previous runs
- Coordinates with coverage registry

##### HTML Report Generator (`html_report.py`)
**Features**:
- Self-contained single-file report
- Embedded screenshots (base64 encoding)
- Interactive expandable test cards
- Detailed step-by-step execution logs
- Assertion results with pass/fail indicators
- Evidence links and previews
- Fallback recovery records
- Filter by test status (all/pass/fail/skip/error)
- Expand/collapse all functionality
- AI summary section with formatted output
- Regression highlighting
- Performance metrics

**Report Sections**:
- Summary statistics (passed/failed/skipped/errors)
- AI-generated summary
- Regression alerts
- Per-test details:
  - Test metadata (name, category, priority, duration)
  - Precondition results
  - Test step results with screenshots
  - Assertion results with evidence
  - Fallback records if recovery occurred
  - Console logs and network activity

##### JSON Report Generator (`json_report.py`)
**Features**:
- Machine-readable format
- Complete test results serialization
- Regression information
- Evidence metadata
- Timestamp and duration data

**Use Cases**:
- CI/CD integration
- Automated processing
- Historical analysis
- Custom reporting tools

---

#### 6. Coverage System (`src/coverage/`)
**Purpose**: Test coverage tracking and gap analysis

##### Coverage Registry (`registry.py`)
**Features**:
- Persists coverage data to `.qa-framework/coverage/registry.json`
- Tracks coverage per page and category
- Maintains test signature history
- Records test results over time
- Configurable history retention (default 20 runs)

**Data Tracked**:
- Page ID → Coverage records
- Category → Test signatures
- Signature → Result history
- Last tested timestamps
- Overall coverage scores

##### Gap Analyzer (`gap_analyzer.py`)
**Purpose**: Identifies testing gaps and priorities

**Identifies**:
- **Untested pages**: Pages with no test coverage
- **Stale pages**: Not tested within threshold (default 7 days)
- **Low coverage areas**: Pages with <50% coverage
- **Recent failures**: Tests that failed in last run
- **Category gaps**: Missing test categories per page

**Output**: Prioritized list of coverage gaps for planner

##### Coverage Scorer (`scorer.py`)
**Purpose**: Calculates coverage metrics

**Metrics**:
- Per-page coverage (0-1)
- Per-category coverage (functional, visual, security)
- Overall framework coverage
- Pages tested / total pages ratio
- Test signature distribution

**Summaries**: Human-readable coverage reports

---

#### 7. AI Integration (`src/ai/`)

##### AI Client (`client.py`)
**Purpose**: Anthropic Claude API wrapper

**Capabilities**:
- Text completions with configurable parameters
- Vision capabilities (image analysis)
- JSON response parsing with fallback strategies
- Markdown code fence stripping
- Retry logic and timeout handling
- Debug logging for failed responses
- Truncation detection and warnings

**Features**:
- Configurable model selection (Sonnet, Opus, Haiku)
- Temperature and token limit controls
- Response validation and error handling
- Call counting and logging
- Parse failure debugging with hex dumps

**Graceful Degradation**: Framework operates without API key

##### Prompt Templates (`prompts/`)

**planning.py**: Test plan generation prompts
- Site model analysis
- Coverage gap incorporation
- Category budget allocation
- Test case structure requirements
- Selector strategy guidance
- Wait time recommendations for visual tests

**fallback.py**: Error recovery prompts
- Failure context description
- Decision framework (retry/adapt/skip/abort)
- Selector correction guidance
- Action adaptation strategies

**summary.py**: Report summary generation
- Test result analysis
- Pattern detection
- Security finding highlights
- Visual regression notes
- Recommendation generation

---

#### 8. Data Models (`src/models/`)

##### Configuration (`config.py`)
**FrameworkConfig**: Master configuration object
- See [Configuration](#configuration) section for complete details

##### Site Model (`site_model.py`)
**Structures**:
- **SiteModel**: Complete site representation
- **Page**: Individual page details
- **Form**: Form analysis results
- **InteractiveElement**: Clickable elements
- **NavigationLink**: Site navigation graph
- **APIEndpoint**: Discovered API endpoints

##### Test Plan (`test_plan.py`)
**Structures**:
- **TestPlan**: Complete test plan
- **TestCase**: Individual test definition
- **Action**: Test step or precondition
- **Assertion**: Verification to perform

##### Test Results (`test_result.py`)
**Structures**:
- **RunResult**: Complete test run results
- **TestResult**: Individual test result
- **StepResult**: Step execution result
- **AssertionResult**: Assertion evaluation result
- **Evidence**: Collected evidence metadata
- **FallbackRecord**: AI recovery attempt

##### Coverage (`coverage.py`)
**Structures**:
- **CoverageRegistry**: Complete coverage data
- **PageCoverage**: Per-page coverage tracking
- **CategoryCoverage**: Per-category statistics
- **SignatureHistory**: Test result history

---

#### 9. CLI Interface (`src/cli.py`)
**Purpose**: Command-line interface using Click framework
- See [CLI Interface](#cli-interface) section for commands

---

## Feature Set

### 1. Automated Site Discovery

**Crawling Capabilities**:
- JavaScript-enabled browser crawling (Playwright)
- Priority-based URL discovery
- Configurable depth and page limits
- Pattern-based URL filtering (include/exclude)
- Same-origin enforcement
- File type filtering
- Sitemap parsing
- SPA route discovery

**Page Analysis**:
- Page type classification
- Interactive element extraction
- Form analysis and field identification
- Navigation graph construction
- Screenshot capture
- DOM snapshot collection
- Network request monitoring
- API endpoint discovery

**SPA Support**:
- Framework detection (React, Vue, Angular, Svelte)
- Client-side routing discovery
- Dynamic content handling
- Hash-based and history API routing

---

### 2. AI-Powered Test Generation

**Planning Features**:
- Contextual test case generation
- Coverage gap-aware planning
- Natural language hint incorporation
- Category budget allocation (functional/visual/security)
- Priority-based test ordering
- Realistic test data generation
- Regression-aware prioritization

**Test Categories**:

**Functional Tests (~50% of budget)**:
- Form submissions (valid/invalid data)
- Navigation flows
- CRUD operations
- Search and filter functionality
- Pagination
- Modal interactions
- Multi-step workflows
- Authentication flows
- Error handling

**Visual Tests (~30% of budget)**:
- Screenshot baseline comparisons
- Responsive layout testing
- Element visibility verification
- Visual regression detection
- Cross-viewport consistency

**Security Tests (~20% of budget)**:
- XSS payload injection
- HTTPS enforcement
- Cookie security attributes
- Open redirect detection
- Error page information leakage
- Response header validation
- Input sanitization verification

---

### 3. Intelligent Test Execution

**Execution Features**:
- Browser automation with Playwright
- Test grouping by target page
- Parallel browser context support (configurable)
- Execution time limits
- Authentication flow handling
- Evidence collection
- Step-by-step result recording
- Console and network log capture

**Action Support**:
- Navigation with configurable wait states
- Element interactions (click, fill, select, hover)
- Scrolling (page and element)
- Keyboard input
- Wait operations (selector or timeout)
- Screenshot capture

**Assertion Support**:
- Element visibility/hidden checks
- Text content verification (contains/equals)
- URL pattern matching
- Visual regression detection
- Element count verification
- Network request validation
- Console error checking
- HTTP status verification

**Error Recovery**:
- AI-assisted fallback on failures
- Screenshot analysis
- DOM inspection
- Selector correction
- Action adaptation
- Configurable retry budget

---

### 4. Visual Regression Testing

**Screenshot Features**:
- Automatic baseline creation on first run
- Page stabilization before capture (network idle + 500ms)
- Viewport or full-page screenshots
- Configurable difference tolerance
- Per-pixel threshold for anti-aliasing
- Baseline persistence and versioning

**Comparison**:
- Pixel-by-pixel comparison
- Anti-aliasing tolerance (40/255 per channel)
- Configurable overall tolerance (default 5%)
- Resize handling for dimension mismatches

**Stability Enhancements**:
- Network idle waiting
- Font loading buffer
- Animation settling time
- Layout shift prevention

---

### 5. Coverage Tracking

**Coverage Registry**:
- Per-page coverage tracking
- Per-category statistics
- Test signature-based history
- Result history retention (configurable)
- Timestamp tracking
- Overall coverage scoring

**Gap Analysis**:
- Untested page identification
- Stale test detection (age-based)
- Low coverage area flagging
- Recent failure surfacing
- Category gap detection

**Metrics**:
- Pages tested / total pages ratio
- Category coverage scores (0-1)
- Overall framework coverage (0-1)
- Test distribution analysis

---

### 6. Comprehensive Reporting

**HTML Reports**:
- Self-contained single file
- Interactive UI with expand/collapse
- Embedded screenshots
- Step-by-step execution details
- Assertion results with evidence
- Fallback recovery records
- AI-generated summaries
- Regression highlighting
- Filter and search functionality
- Performance metrics

**JSON Reports**:
- Machine-readable format
- Complete data serialization
- CI/CD integration support
- Historical analysis capability

**AI Summaries**:
- Natural language test analysis
- Key failure pattern identification
- Security finding highlights
- Visual regression notes
- Actionable recommendations

**Regression Detection**:
- Pass→fail transition tracking
- Failure reason capture
- Historical comparison
- Report highlighting

---

### 7. Authentication Support

**Login Flows**:
- Configurable login URLs
- Username/password credentials
- Selector-based form filling
- Success indicator validation
- Session persistence
- Environment variable support for passwords

---

### 8. Responsive Testing

**Viewport Support**:
- Multiple viewport configurations
- Desktop, tablet, mobile presets
- Custom dimensions
- Per-viewport test execution
- Responsive layout verification

---

### 9. Security Testing

**XSS Testing**:
- Configurable payload library
- Form field injection
- Script execution detection
- Console error validation
- Output sanitization verification

**Security Checks**:
- HTTPS enforcement
- Cookie security attributes
- Open redirect detection
- Error information leakage
- Response header validation

---

## AI Integration

### AI Features

#### 1. Test Plan Generation
**Model**: Claude (Sonnet/Opus/Haiku selectable)
**Input**: Site model, coverage gaps, hints
**Output**: Structured test plan with contextual test cases

**Capabilities**:
- Analyzes page structure and elements
- Identifies testing opportunities
- Generates realistic test data
- Allocates tests across categories
- Incorporates user hints
- Respects budget constraints

**Prompt Engineering**:
- Structured JSON schema enforcement
- Category-specific guidance
- Selector strategy instruction
- Visual test stabilization requirements

#### 2. Error Recovery (Fallback Handler)
**Model**: Claude with Vision
**Input**: Failed step context (screenshot, DOM, console logs, action details)
**Output**: Recovery decision with reasoning

**Decisions**:
- **Retry**: Provides corrected selector
- **Adapt**: Suggests alternative action
- **Skip**: Recommends skipping step
- **Abort**: Declares test unrecoverable

**Vision Analysis**:
- Screenshots analyzed for page state
- Element location identification
- Error message detection
- Layout understanding

#### 3. Report Summaries
**Model**: Claude (Sonnet/Opus)
**Input**: Test results, coverage data, regressions
**Output**: Natural language summary

**Highlights**:
- Key failures and patterns
- Security findings
- Visual regressions
- Performance issues
- Recommendations

### Fallback Mechanisms

**Without API Key**:
- Basic test plan generation (template-based)
- No AI summaries
- No fallback recovery
- Full test execution capability maintained

**API Failures**:
- Retry logic with exponential backoff
- Timeout handling (30 minutes for planning)
- Graceful degradation
- Error logging and debugging

---

## Configuration

### Configuration File: `qa-config.json`

#### Required Settings

```json
{
  "target_url": "https://example.com"
}
```

#### Optional Settings

##### Authentication
```json
"auth": {
  "login_url": "https://example.com/login",
  "username": "user@example.com",
  "password": "env:QA_TEST_PASSWORD",  // Use env var
  "username_selector": "#email",
  "password_selector": "#password",
  "submit_selector": "#login-button",
  "success_indicator": ".dashboard"
}
```

##### Crawl Configuration
```json
"crawl": {
  "target_url": "https://example.com",
  "max_pages": 50,
  "max_depth": 5,
  "include_patterns": ["^https://example\\.com/products/.*"],
  "exclude_patterns": ["^https://example\\.com/admin/.*"],
  "auth_credentials": { /* same as auth */ },
  "wait_for_idle": true,
  "viewport": {
    "width": 1280,
    "height": 720,
    "name": "desktop"
  },
  "user_agent": "Mozilla/5.0 ..."
}
```

##### Test Categories
```json
"categories": ["functional", "visual", "security"]
```

##### Execution Limits
```json
"max_tests_per_run": 100,
"max_execution_time_seconds": 1800,  // 30 minutes
"max_parallel_contexts": 3
```

##### AI Configuration
```json
"ai_model": "claude-opus-4-6",
"ai_max_fallback_calls_per_test": 3,
"ai_max_planning_tokens": 32000
```

##### Coverage Settings
```json
"staleness_threshold_days": 7,
"history_retention_runs": 20
```

##### Visual Testing
```json
"visual_diff_tolerance": 0.15,  // 15% difference allowed
"viewports": [
  {"width": 1280, "height": 720, "name": "desktop"},
  {"width": 768, "height": 1024, "name": "tablet"},
  {"width": 375, "height": 812, "name": "mobile"}
]
```

##### Security Testing
```json
"security_xss_payloads": [
  "<script>alert(1)</script>",
  "\"><img src=x onerror=alert(1)>",
  "javascript:alert(1)",
  "'-alert(1)-'",
  "<svg onload=alert(1)>"
],
"security_max_probe_depth": 2
```

##### Reporting
```json
"report_formats": ["html", "json"],
"report_output_dir": "./qa-reports",
"capture_video": false
```

##### URL Filtering
```json
"include_url_patterns": ["^https://example\\.com/.*"],
"exclude_url_patterns": ["^https://example\\.com/admin/.*"]
```

##### Planning Hints
```json
"hints": [
  "Create vault with guaranteed unique name then login as that vault id",
  "When creating a new vault there is a one time step with a Secure Diceware Passphrase",
  "All matchers should be case insensitive"
]
```

---

## Test Types & Assertions

### Test Case Structure

```json
{
  "test_id": "tc_001",
  "name": "Human-readable test name",
  "description": "What this test verifies",
  "category": "functional | visual | security",
  "priority": 1-5,  // 1=critical, 5=low
  "target_page_id": "page_id_from_site_model",
  "coverage_signature": "unique_test_signature",
  "preconditions": [/* Action objects */],
  "steps": [/* Action objects */],
  "assertions": [/* Assertion objects */],
  "timeout_seconds": 30
}
```

### Action Types

#### navigate
```json
{
  "action_type": "navigate",
  "selector": null,
  "value": "https://example.com/page",
  "description": "Navigate to target page"
}
```

#### click
```json
{
  "action_type": "click",
  "selector": "#submit-button",
  "value": null,
  "description": "Click submit button"
}
```

#### fill
```json
{
  "action_type": "fill",
  "selector": "#email-input",
  "value": "user@example.com",
  "description": "Enter email address"
}
```

#### select
```json
{
  "action_type": "select",
  "selector": "#country-select",
  "value": "USA",
  "description": "Select country from dropdown"
}
```

#### hover
```json
{
  "action_type": "hover",
  "selector": ".dropdown-trigger",
  "value": null,
  "description": "Hover over dropdown menu"
}
```

#### scroll
```json
{
  "action_type": "scroll",
  "selector": "#footer",  // or null for page scroll
  "value": "1000",  // or null for element scroll
  "description": "Scroll to footer"
}
```

#### wait
```json
{
  "action_type": "wait",
  "selector": ".loading-spinner",  // wait for selector
  "value": "2000",  // or timeout in ms
  "description": "Wait for loading to complete"
}
```

#### keyboard
```json
{
  "action_type": "keyboard",
  "selector": null,
  "value": "Enter",
  "description": "Press Enter key"
}
```

#### screenshot
```json
{
  "action_type": "screenshot",
  "selector": null,
  "value": "screenshot_name",
  "description": "Capture screenshot"
}
```

### Assertion Types

#### element_visible
```json
{
  "assertion_type": "element_visible",
  "selector": "#success-message",
  "expected_value": null,
  "tolerance": null,
  "description": "Success message should be visible"
}
```

#### element_hidden
```json
{
  "assertion_type": "element_hidden",
  "selector": "#loading-spinner",
  "expected_value": null,
  "tolerance": null,
  "description": "Loading spinner should be hidden"
}
```

#### text_contains
```json
{
  "assertion_type": "text_contains",
  "selector": "body",  // or specific element
  "expected_value": "Welcome back",
  "tolerance": null,
  "description": "Page contains welcome message"
}
```

#### text_equals
```json
{
  "assertion_type": "text_equals",
  "selector": "h1",
  "expected_value": "Dashboard",
  "tolerance": null,
  "description": "Heading is exactly 'Dashboard'"
}
```

#### url_matches
```json
{
  "assertion_type": "url_matches",
  "selector": null,
  "expected_value": "/dashboard",  // substring or regex
  "tolerance": null,
  "description": "URL should contain /dashboard"
}
```

#### screenshot_diff
```json
{
  "assertion_type": "screenshot_diff",
  "selector": null,
  "expected_value": "full_page",  // or null for viewport
  "tolerance": 0.05,  // or null for config default
  "description": "Visual baseline should match"
}
```

#### element_count
```json
{
  "assertion_type": "element_count",
  "selector": ".product-card",
  "expected_value": "12",
  "tolerance": null,
  "description": "Should have 12 product cards"
}
```

#### network_request_made
```json
{
  "assertion_type": "network_request_made",
  "selector": null,
  "expected_value": "/api/user/profile",
  "tolerance": null,
  "description": "Profile API should be called"
}
```

#### no_console_errors
```json
{
  "assertion_type": "no_console_errors",
  "selector": null,
  "expected_value": null,
  "tolerance": null,
  "description": "No JavaScript errors should occur"
}
```

#### response_status
```json
{
  "assertion_type": "response_status",
  "selector": null,
  "expected_value": "200",
  "tolerance": null,
  "description": "API should return 200 OK"
}
```

---

## Reporting & Coverage

### HTML Report Features

**Summary Section**:
- Total tests executed
- Pass/fail/skip/error counts
- Execution duration
- Target URL
- Run ID and timestamp

**AI Summary**:
- Natural language analysis
- Key findings
- Pattern detection
- Recommendations
- Formatted with line breaks

**Regressions**:
- Pass→fail transitions
- Previous vs. current results
- Failure reasons

**Test Cards** (expandable/collapsible):
- Test metadata (name, category, priority)
- Result badge (pass/fail/skip/error)
- Duration
- Assertion pass/fail count
- Description
- Precondition results
- Step-by-step execution:
  - Step description
  - Screenshot (if available)
  - Status indicator
  - Error messages
- Assertion results:
  - Assertion type and description
  - Expected vs. actual
  - Pass/fail status
  - Evidence
- Fallback records:
  - Decision made
  - Reasoning
  - New selector/action

**Filtering**:
- All tests
- Passed only
- Failed only
- Skipped only
- Errors only

**Controls**:
- Expand all / Collapse all
- Filter by status

### JSON Report Structure

```json
{
  "run_id": "run_abc123",
  "target_url": "https://example.com",
  "started_at": "2025-01-15T12:00:00Z",
  "duration_seconds": 450.2,
  "total_tests": 25,
  "passed": 20,
  "failed": 3,
  "skipped": 1,
  "errors": 1,
  "test_results": [/* TestResult objects */],
  "ai_summary": "Natural language summary...",
  "regressions": [/* Regression objects */]
}
```

### Coverage Registry Structure

```json
{
  "last_updated": "2025-01-15T12:00:00Z",
  "overall_coverage": 0.85,
  "pages_tested": 40,
  "total_pages": 47,
  "category_scores": {
    "functional": 0.90,
    "visual": 0.75,
    "security": 0.60
  },
  "page_coverage": {
    "page_001": {
      "page_id": "page_001",
      "url": "https://example.com",
      "overall_score": 0.95,
      "last_tested": "2025-01-15T11:30:00Z",
      "category_coverage": {
        "functional": {/* signatures and history */},
        "visual": {/* signatures and history */},
        "security": {/* signatures and history */}
      }
    }
  },
  "last_full_run": "run_abc123"
}
```

### Coverage Metrics

**Page Coverage**:
- Calculated as: signatures_tested / expected_signatures_per_category
- Averaged across categories

**Category Coverage**:
- Functional: Form submissions, navigation, CRUD ops
- Visual: Screenshot baselines, layout checks
- Security: XSS, HTTPS, cookies, headers

**Overall Coverage**:
- Weighted average of all page coverages
- Considers page importance (forms > static pages)

**Staleness**:
- Page marked stale if not tested in N days (configurable)
- Prioritized in gap analysis

---

## CLI Interface

### Pipeline Commands

#### Full Pipeline
```bash
python -m src.cli run
python -m src.cli run -c custom-config.json
python -m src.cli run --verbose
```

#### Individual Stages
```bash
# Crawl only
python -m src.cli crawl

# Plan only (requires existing site model)
python -m src.cli plan

# Execute specific plan
python -m src.cli execute --plan-file .qa-framework/latest_plan.json
```

### Coverage Commands

```bash
# View coverage summary
python -m src.cli coverage

# View coverage gaps
python -m src.cli coverage --gaps

# Reset coverage data
python -m src.cli coverage --reset
```

### Initialization

```bash
# Create default config
python -m src.cli init --target https://example.com

# Creates qa-config.json with defaults
```

### Hint Management

```bash
# Add planning hint
python -m src.cli hint add "Prioritize checkout flow"

# List hints
python -m src.cli hint list

# Clear all hints
python -m src.cli hint clear
```

### Global Options

```bash
-c, --config PATH      Config file path (default: qa-config.json)
-v, --verbose          Enable debug logging
-p, --plan-file PATH   Test plan file for execute command
```

---

## Technical Specifications

### System Requirements

**Python**: 3.10 or higher

**Dependencies**:
- playwright >= 1.40.0
- anthropic >= 0.39.0
- pydantic >= 2.5.0
- click >= 8.1.0
- jinja2 >= 3.1.0
- Pillow >= 10.0.0
- aiofiles >= 23.0.0
- rich >= 13.0.0

**Browser**: Chromium (installed via Playwright)

### Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...           # Required for AI features
QA_TEST_PASSWORD=secret123             # For auth config
# Custom env vars can be referenced: env:VARIABLE_NAME
```

### Directory Structure

```
project/
├── qa-config.json                     # Main configuration
├── .qa-framework/                     # Framework data
│   ├── site_model/
│   │   └── model.json                # Crawl output
│   ├── coverage/
│   │   └── registry.json             # Coverage data
│   ├── latest_plan.json              # Most recent test plan
│   └── debug/                        # Debug logs
│       ├── ai_call_*.log
│       └── parse_failure_*.log
├── qa-reports/                        # Test reports
│   ├── report_run_*.html
│   └── report_run_*.json
└── .qa-framework/runs/                # Test execution data
    └── run_*/
        ├── evidence/                  # Screenshots, logs
        └── test_*/
            ├── screenshots/
            ├── console.log
            └── network.log
```

### Performance Considerations

**Crawl Performance**:
- Parallel page processing not implemented (sequential)
- Network idle waiting can add 3-10s per page
- Typical crawl: 50 pages in 5-10 minutes

**Test Execution**:
- Parallel context support (configurable, default 3)
- Test grouping by page reduces navigation overhead
- Typical execution: 20 tests in 10-15 minutes

**AI API Calls**:
- Planning: 1 call per run (can take 30-60s with large sites)
- Fallback: Up to N calls per test (N=max_fallback_calls_per_test)
- Summaries: 1 call per run (5-10s)

**Token Usage**:
- Planning: Up to 32,000 output tokens (configurable)
- Site model summarization reduces input tokens
- Fallback: ~1,000-2,000 tokens per call

### Limitations

**Browser Support**:
- Chromium only (via Playwright)
- No Firefox or WebKit support currently

**Authentication**:
- Simple form-based auth only
- No OAuth, SAML, or multi-factor auth
- Single auth flow per run

**Crawling**:
- Same-origin only
- No cross-domain crawling
- No subdomain discovery

**Visual Testing**:
- No animated content handling (waits for stability)
- No dynamic content masking
- No perceptual diff algorithms (pixel-based only)

**Parallel Execution**:
- Parallel contexts only (not parallel tests across contexts)
- No distributed execution

**Test Generation**:
- Requires AI API for intelligent tests
- Fallback plans are basic/template-based

### Security Considerations

**Credentials**:
- Passwords stored in config or env vars
- No encryption at rest
- Recommend env vars for sensitive data

**Evidence Collection**:
- Screenshots may contain sensitive data
- Console logs may contain API keys
- Network logs may contain auth tokens
- Evidence stored unencrypted

**AI Integration**:
- Screenshots sent to Claude API
- DOM snippets sent to Claude API
- No data retention by Anthropic (as of API ToS)

### Error Handling

**Crawler Errors**:
- Page timeout → Skip page, continue crawling
- Navigation failure → Log error, continue
- JavaScript error → Capture in console logs

**Execution Errors**:
- Step failure → Invoke fallback (if available) or mark failed
- Timeout → Mark step failed, continue test
- Browser crash → Terminate test, continue with next

**AI Errors**:
- API timeout → Skip AI feature, continue
- Invalid JSON → Log debug info, use fallback
- Rate limit → Exponential backoff, retry

**Reporting Errors**:
- Evidence file missing → Show placeholder
- Report generation failure → Log error, generate partial report

### Extensibility

**Adding Action Types**:
1. Add case in `action_runner.py::run_action()`
2. Update schema in `test_plan.py::Action`
3. Update planning prompt with examples

**Adding Assertion Types**:
1. Add checker function in `assertion_checker.py`
2. Add case in `check_assertion()`
3. Update schema in `test_plan.py::Assertion`
4. Update planning prompt

**Custom Reporters**:
1. Implement reporter class
2. Add to `reporter.py` format handling
3. Update config schema

**Custom Scorers**:
1. Implement scorer in `coverage/scorer.py`
2. Hook into registry updates
3. Add to coverage reports

---

## Appendices

### A. Example Test Plan

```json
{
  "plan_id": "tp_example_001",
  "generated_at": "2025-01-15T12:00:00Z",
  "target_url": "https://example.com",
  "test_cases": [
    {
      "test_id": "tc_001",
      "name": "Login with valid credentials",
      "description": "Verify successful login with correct username and password",
      "category": "functional",
      "priority": 1,
      "target_page_id": "page_login",
      "coverage_signature": "login_valid_credentials",
      "preconditions": [
        {
          "action_type": "navigate",
          "selector": null,
          "value": "https://example.com/login",
          "description": "Navigate to login page"
        }
      ],
      "steps": [
        {
          "action_type": "fill",
          "selector": "#username",
          "value": "testuser@example.com",
          "description": "Enter username"
        },
        {
          "action_type": "fill",
          "selector": "#password",
          "value": "SecureP@ss123",
          "description": "Enter password"
        },
        {
          "action_type": "click",
          "selector": "#login-button",
          "value": null,
          "description": "Click login button"
        },
        {
          "action_type": "wait",
          "selector": null,
          "value": "2000",
          "description": "Wait for navigation"
        }
      ],
      "assertions": [
        {
          "assertion_type": "url_matches",
          "selector": null,
          "expected_value": "/dashboard",
          "tolerance": null,
          "description": "Should redirect to dashboard"
        },
        {
          "assertion_type": "element_visible",
          "selector": ".user-profile",
          "expected_value": null,
          "tolerance": null,
          "description": "User profile should be visible"
        },
        {
          "assertion_type": "no_console_errors",
          "selector": null,
          "expected_value": null,
          "tolerance": null,
          "description": "No console errors during login"
        }
      ],
      "timeout_seconds": 30
    }
  ],
  "estimated_duration_seconds": 45,
  "coverage_intent": {
    "functional": 15,
    "visual": 8,
    "security": 2
  }
}
```

### B. Example Site Model (Excerpt)

```json
{
  "base_url": "https://example.com",
  "pages": [
    {
      "page_id": "page_001",
      "url": "https://example.com/",
      "type": "listing",
      "title": "Home - Example Site",
      "interactive_elements": [
        {
          "element_id": "elem_001",
          "type": "button",
          "text": "Get Started",
          "selector": "#cta-button",
          "role": "button"
        }
      ],
      "forms": [
        {
          "form_id": "form_001",
          "action": "/search",
          "method": "GET",
          "fields": [
            {
              "name": "q",
              "type": "text",
              "required": true,
              "label": "Search",
              "selector": "#search-input"
            }
          ]
        }
      ],
      "screenshot_path": ".qa-framework/site_model/screenshots/page_001.png"
    }
  ],
  "navigation": [
    {
      "from_page_id": "page_001",
      "to_page_id": "page_002",
      "link_text": "About",
      "selector": "a[href='/about']"
    }
  ],
  "api_endpoints": [
    {
      "url": "https://example.com/api/products",
      "method": "GET",
      "discovered_on": "page_001"
    }
  ]
}
```

---

## Version History

**v1.0.0** - Initial release
- Complete crawl/plan/execute/report pipeline
- AI integration (Claude Sonnet/Opus/Haiku)
- Visual regression testing
- Coverage tracking
- Fallback mechanisms
- HTML/JSON reporting

---

## License

[Insert License Information]

---

## Support

For issues, feature requests, or questions:
- GitHub Issues: [Repository URL]
- Documentation: [Docs URL]
- Email: [Support Email]

---

## Contributing

[Insert Contributing Guidelines]

---

**End of Requirements Documentation**
