"""HTML report generator — produces a self-contained HTML report with full test detail."""

from __future__ import annotations

import base64
import html
import logging
from pathlib import Path

from src.models.coverage import CoverageRegistry
from src.models.test_result import RunResult, TestResult

from .regression_detector import Regression

logger = logging.getLogger(__name__)


def _embed_image(path: str) -> str:
    """Read an image file and return a base64 data URI, or empty string on failure."""
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            return ""
        with open(p, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        suffix = p.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/webp"
        return f"data:{mime};base64,{data}"
    except Exception:
        return ""


def _step_icon(status: str) -> str:
    if status == "pass":
        return '<span class="step-icon pass-icon">&#10003;</span>'
    elif status == "fail":
        return '<span class="step-icon fail-icon">&#10007;</span>'
    return '<span class="step-icon skip-icon">&#8212;</span>'


def _build_test_card(r: TestResult) -> str:
    """Build a detailed HTML card for a single test result."""
    result_class = r.result
    border_color = {"pass": "#22c55e", "fail": "#ef4444", "skip": "#eab308", "error": "#f97316"}.get(r.result, "#94a3b8")

    # Header
    card = f'''
    <div class="test-card" id="test-{html.escape(r.test_id)}">
      <div class="test-header" style="border-left: 4px solid {border_color};" onclick="this.parentElement.classList.toggle('expanded')">
        <div class="test-header-left">
          <span class="badge {result_class}">{r.result.upper()}</span>
          {'<span class="badge flaky">POTENTIALLY FLAKY</span>' if r.potentially_flaky else ''}
          <strong>{html.escape(r.test_name)}</strong>
          <span class="badge {r.category}">{r.category}</span>
          <span class="test-meta">P{r.priority} &middot; {r.duration_seconds:.1f}s &middot; {r.assertions_passed}/{r.assertions_total} assertions</span>
        </div>
        <span class="expand-arrow">&#9660;</span>
      </div>
      <div class="test-body">
    '''

    # Description
    if r.description:
        card += f'<div class="test-description">{html.escape(r.description)}</div>'

    # Failure reason (prominent)
    if r.failure_reason:
        card += f'<div class="failure-banner"><strong>Failure:</strong> {html.escape(r.failure_reason)}</div>'

    # Flaky detection notice
    if r.potentially_flaky:
        card += ('<div class="flaky-banner"><strong>Potentially Flaky:</strong> '
                 'This test failed initially but passed on a video re-run. '
                 'The attached video shows the successful re-run.</div>')

    # --- Preconditions ---
    if r.precondition_results:
        card += '<div class="section"><h4>Preconditions</h4><div class="steps-list">'
        for sr in r.precondition_results:
            card += _build_step_row(sr)
        card += '</div></div>'

    # --- Test Steps ---
    if r.step_results:
        card += '<div class="section"><h4>Test Steps</h4><div class="steps-list">'
        for sr in r.step_results:
            card += _build_step_row(sr)
        card += '</div></div>'

    # --- Assertions ---
    if r.assertion_results:
        card += '<div class="section"><h4>Assertions</h4><div class="assertions-list">'
        for ar in r.assertion_results:
            icon = _step_icon("pass" if ar.passed else "fail")
            desc = html.escape(ar.description or ar.assertion_type)
            msg = html.escape(ar.message) if ar.message else ""
            expected = ""
            if ar.expected_value:
                expected = f' <span class="assert-expected">expected: {html.escape(ar.expected_value)}</span>'
            if ar.selector:
                expected += f' <span class="assert-selector">selector: <code>{html.escape(ar.selector)}</code></span>'

            row_class = "assert-pass" if ar.passed else "assert-fail"
            card += f'''
            <div class="assert-row {row_class}">
              {icon}
              <div class="assert-content">
                <div class="assert-desc">{desc}{expected}</div>
                {"<div class='assert-msg'>" + msg + "</div>" if msg else ""}
              </div>
            </div>'''
        card += '</div></div>'

    # --- AI Fallback Records ---
    if r.fallback_records:
        card += '<div class="section"><h4>AI Fallback Decisions</h4><div class="fallback-list">'
        for fb in r.fallback_records:
            card += f'''
            <div class="fallback-row">
              <span class="badge skip">Step {fb.step_index}: {html.escape(fb.decision)}</span>
              <span>{html.escape(fb.reasoning)}</span>
              {f"<br><code>Original: {html.escape(fb.original_selector)}</code>" if fb.original_selector else ""}
              {f"<br><code>New: {html.escape(fb.new_selector)}</code>" if fb.new_selector else ""}
            </div>'''
        card += '</div></div>'

    # --- Screenshots ---
    evidence_images = [s for s in r.evidence.screenshots if s]
    if evidence_images:
        card += '<div class="section"><h4>Screenshots</h4><div class="screenshots-grid">'
        for img_path in evidence_images:
            data_uri = _embed_image(img_path)
            if data_uri:
                label = Path(img_path).stem
                card += f'''
                <div class="screenshot-item">
                  <img src="{data_uri}" alt="{html.escape(label)}" loading="lazy" onclick="this.classList.toggle('zoomed')"/>
                  <div class="screenshot-label">{html.escape(label)}</div>
                </div>'''
        card += '</div></div>'

    # --- Video Recording ---
    if r.evidence.video_path:
        video_name = html.escape(Path(r.evidence.video_path).name)
        video_abs = html.escape(str(Path(r.evidence.video_path).resolve()))
        card += f'''<div class="section video-section"><h4>Video Recording</h4>
          <video controls preload="metadata">
            <source src="file:///{video_abs}" type="video/webm">
            Your browser does not support the video tag.
          </video>
          <div class="screenshot-label">{video_name}</div>
        </div>'''

    # --- Console Errors ---
    console_errors = [log for log in r.evidence.console_logs if "[error]" in log.lower()]
    if console_errors:
        card += '<div class="section"><h4>Console Errors</h4><pre class="console-log">'
        for err in console_errors[:20]:
            card += html.escape(err) + "\n"
        card += '</pre></div>'

    card += '</div></div>'  # close test-body and test-card
    return card


def _build_step_row(sr) -> str:
    """Build a single step result row."""
    icon = _step_icon(sr.status)
    action_label = html.escape(sr.action_type)
    desc = html.escape(sr.description or "")
    selector_html = f"<code>{html.escape(sr.selector)}</code>" if sr.selector else ""
    value_html = f'<span class="step-value">"{html.escape(sr.value)}"</span>' if sr.value else ""

    error_html = ""
    if sr.error_message:
        error_html = f'<div class="step-error">{html.escape(sr.error_message[:300])}</div>'

    # Inline screenshot thumbnail
    thumb_html = ""
    if sr.screenshot_path:
        data_uri = _embed_image(sr.screenshot_path)
        if data_uri:
            thumb_html = f'<img class="step-thumb" src="{data_uri}" alt="step screenshot" onclick="this.classList.toggle(\'zoomed\')"/>'

    return f'''
    <div class="step-row step-{sr.status}">
      {icon}
      <div class="step-content">
        <span class="step-action">{action_label}</span>
        {selector_html} {value_html}
        <span class="step-desc">{desc}</span>
        {error_html}
      </div>
      {thumb_html}
    </div>'''


def generate_html_report(
    run_result: RunResult,
    regressions: list[Regression],
    registry: CoverageRegistry | None,
    output_path: Path,
) -> None:
    """Generate a self-contained HTML report with detailed test cards."""

    # AI Summary
    ai_section = ""
    if run_result.ai_summary:
        # Format the summary with preserved line breaks and better structure
        formatted_summary = html.escape(run_result.ai_summary).replace('\n', '<br>')
        ai_section = f'<div class="ai-summary"><h2>&#129302; AI Summary</h2><div class="summary-content">{formatted_summary}</div></div>'

    # Regressions
    reg_section = ""
    if regressions:
        items = ""
        for r in regressions:
            reason = f" &mdash; {html.escape(r.failure_reason)}" if r.failure_reason else ""
            items += f"<li><strong>{html.escape(r.test_name)}</strong> ({r.category}): {r.previous_result} &rarr; {r.current_result}{reason}</li>"
        reg_section = f'<div class="regressions"><h2>&#9888; Regressions ({len(regressions)})</h2><ul>{items}</ul></div>'

    # Test cards
    test_cards = []
    for r in run_result.test_results:
        test_cards.append(_build_test_card(r))

    report_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QA Report &mdash; {html.escape(run_result.run_id)}</title>
<style>
  :root {{ --pass: #22c55e; --fail: #ef4444; --skip: #eab308; --error: #f97316; --bg: #f8fafc; --card: white; --border: #e2e8f0; --text: #1e293b; --muted: #64748b; --accent: #6366f1; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 1.5rem; }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.3rem; }}
  .meta {{ color: var(--muted); margin-bottom: 1.5rem; font-size: 0.9rem; }}
  /* Summary cards */
  .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.8rem; margin-bottom: 1.5rem; }}
  .stat {{ background: var(--card); border-radius: 8px; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; }}
  .stat .value {{ font-size: 1.8rem; font-weight: 700; }}
  .stat .label {{ font-size: 0.8rem; color: var(--muted); }}
  .stat.pass .value {{ color: var(--pass); }}
  .stat.fail .value {{ color: var(--fail); }}
  .stat.skip .value {{ color: var(--skip); }}
  .stat.error .value {{ color: var(--error); }}
  /* Badges */
  .badge {{ display: inline-block; padding: 0.15rem 0.55rem; border-radius: 9999px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; white-space: nowrap; }}
  .badge.pass {{ background: #dcfce7; color: #166534; }}
  .badge.fail, .badge.FAIL {{ background: #fecaca; color: #991b1b; }}
  .badge.skip {{ background: #fef9c3; color: #854d0e; }}
  .badge.error {{ background: #fed7aa; color: #9a3412; }}
  .badge.functional {{ background: #dbeafe; color: #1e40af; }}
  .badge.visual {{ background: #e0e7ff; color: #3730a3; }}
  .badge.security {{ background: #fce7f3; color: #9d174d; }}
  /* AI / Regression boxes */
  .ai-summary {{ background: var(--card); border-radius: 8px; padding: 1.2rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-left: 4px solid var(--accent); }}
  .ai-summary h2 {{ font-size: 1rem; color: var(--accent); margin-bottom: 0.8rem; }}
  .summary-content {{ font-size: 0.9rem; line-height: 1.7; color: var(--text); }}
  .regressions {{ background: #fef2f2; border-radius: 8px; padding: 1.2rem; margin-bottom: 1.5rem; border-left: 4px solid var(--fail); }}
  .regressions h2 {{ color: var(--fail); font-size: 1rem; margin-bottom: 0.4rem; }}
  .regressions ul {{ margin-left: 1.2rem; font-size: 0.9rem; }}
  /* Test cards */
  .test-card {{ background: var(--card); border-radius: 8px; margin-bottom: 0.6rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden; }}
  .test-header {{ display: flex; justify-content: space-between; align-items: center; padding: 0.7rem 1rem; cursor: pointer; user-select: none; }}
  .test-header:hover {{ background: #f8fafc; }}
  .test-header-left {{ display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }}
  .test-meta {{ font-size: 0.78rem; color: var(--muted); }}
  .expand-arrow {{ color: var(--muted); font-size: 0.7rem; transition: transform 0.2s; }}
  .test-card.expanded .expand-arrow {{ transform: rotate(180deg); }}
  .test-body {{ display: none; padding: 0 1rem 1rem 1rem; }}
  .test-card.expanded .test-body {{ display: block; }}
  .test-description {{ color: var(--muted); font-size: 0.88rem; margin-bottom: 0.8rem; padding: 0.5rem; background: #f1f5f9; border-radius: 4px; }}
  .failure-banner {{ background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; border-radius: 6px; padding: 0.6rem 0.8rem; margin-bottom: 0.8rem; font-size: 0.88rem; }}
  .section {{ margin-bottom: 1rem; }}
  .section h4 {{ font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; padding-bottom: 0.25rem; border-bottom: 1px solid var(--border); }}
  /* Steps */
  .step-row {{ display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.35rem 0; border-bottom: 1px solid #f1f5f9; font-size: 0.85rem; }}
  .step-row:last-child {{ border-bottom: none; }}
  .step-icon {{ width: 18px; height: 18px; display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 0.7rem; flex-shrink: 0; margin-top: 2px; }}
  .pass-icon {{ background: #dcfce7; color: #166534; }}
  .fail-icon {{ background: #fecaca; color: #991b1b; }}
  .skip-icon {{ background: #f1f5f9; color: #64748b; }}
  .step-content {{ flex: 1; }}
  .step-action {{ background: #f1f5f9; padding: 0.1rem 0.4rem; border-radius: 3px; font-family: monospace; font-size: 0.8rem; font-weight: 600; }}
  .step-content code {{ background: #f1f5f9; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.8rem; }}
  .step-value {{ color: var(--accent); font-size: 0.82rem; }}
  .step-desc {{ color: var(--muted); font-size: 0.82rem; }}
  .step-error {{ color: var(--fail); font-size: 0.82rem; margin-top: 0.15rem; }}
  .step-thumb {{ width: 80px; height: 50px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border); cursor: pointer; flex-shrink: 0; }}
  .step-thumb.zoomed {{ position: fixed; top: 5%; left: 5%; width: 90%; height: 90%; object-fit: contain; z-index: 1000; background: rgba(0,0,0,0.85); border: none; border-radius: 8px; padding: 1rem; }}
  /* Assertions */
  .assert-row {{ display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.35rem 0; border-bottom: 1px solid #f1f5f9; font-size: 0.85rem; }}
  .assert-row:last-child {{ border-bottom: none; }}
  .assert-pass {{ }}
  .assert-fail {{ background: #fef8f8; }}
  .assert-content {{ flex: 1; }}
  .assert-desc {{ }}
  .assert-expected {{ color: var(--muted); font-size: 0.8rem; }}
  .assert-selector {{ color: var(--muted); font-size: 0.8rem; }}
  .assert-msg {{ font-size: 0.82rem; color: var(--fail); margin-top: 0.1rem; }}
  .assert-msg .assert-pass .assert-msg {{ color: var(--pass); }}
  /* Fallback */
  .fallback-row {{ padding: 0.4rem 0; font-size: 0.85rem; border-bottom: 1px solid #f1f5f9; }}
  .fallback-row code {{ font-size: 0.8rem; background: #f1f5f9; padding: 0.1rem 0.3rem; border-radius: 3px; }}
  /* Flaky */
  .badge.flaky {{ background: #fef3c7; color: #92400e; border: 1px dashed #f59e0b; }}
  .flaky-banner {{ background: #fefce8; border: 1px solid #fde68a; color: #92400e; border-radius: 6px; padding: 0.6rem 0.8rem; margin-bottom: 0.8rem; font-size: 0.88rem; }}
  /* Video */
  .video-section video {{ width: 100%; max-width: 640px; border-radius: 6px; border: 1px solid var(--border); }}
  /* Screenshots */
  .screenshots-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.6rem; }}
  .screenshot-item {{ text-align: center; }}
  .screenshot-item img {{ width: 100%; border-radius: 6px; border: 1px solid var(--border); cursor: pointer; }}
  .screenshot-item img.zoomed {{ position: fixed; top: 5%; left: 5%; width: 90%; height: 90%; object-fit: contain; z-index: 1000; background: rgba(0,0,0,0.85); border: none; border-radius: 8px; padding: 1rem; }}
  .screenshot-label {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.2rem; }}
  /* Console */
  .console-log {{ background: #1e293b; color: #f1f5f9; padding: 0.8rem; border-radius: 6px; font-size: 0.78rem; overflow-x: auto; max-height: 200px; overflow-y: auto; }}
  /* Filter bar */
  .filter-bar {{ display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }}
  .filter-btn {{ padding: 0.3rem 0.8rem; border-radius: 6px; border: 1px solid var(--border); background: var(--card); cursor: pointer; font-size: 0.82rem; }}
  .filter-btn.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
</style>
</head>
<body>
<div class="container">
  <h1>QA Test Report</h1>
  <p class="meta">Run: {html.escape(run_result.run_id)} &middot; Target: {html.escape(run_result.target_url)} &middot; {html.escape(run_result.started_at)} &middot; Duration: {run_result.duration_seconds}s</p>

  <div class="summary">
    <div class="stat"><div class="value">{run_result.total_tests}</div><div class="label">Total Tests</div></div>
    <div class="stat pass"><div class="value">{run_result.passed}</div><div class="label">Passed</div></div>
    <div class="stat fail"><div class="value">{run_result.failed}</div><div class="label">Failed</div></div>
    <div class="stat skip"><div class="value">{run_result.skipped}</div><div class="label">Skipped</div></div>
    <div class="stat error"><div class="value">{run_result.errors}</div><div class="label">Errors</div></div>
  </div>

  {ai_section}
  {reg_section}

  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterTests('all')">All</button>
    <button class="filter-btn" onclick="filterTests('fail')">Failed</button>
    <button class="filter-btn" onclick="filterTests('error')">Errors</button>
    <button class="filter-btn" onclick="filterTests('pass')">Passed</button>
    <button class="filter-btn" onclick="filterTests('skip')">Skipped</button>
    <button class="filter-btn" onclick="expandAll()">Expand All</button>
    <button class="filter-btn" onclick="collapseAll()">Collapse All</button>
  </div>

  <div id="test-list">
    {"".join(test_cards)}
  </div>
</div>

<script>
function filterTests(status) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.test-card').forEach(card => {{
    if (status === 'all') {{ card.style.display = ''; return; }}
    const badge = card.querySelector('.test-header .badge');
    card.style.display = badge && badge.textContent.trim().toLowerCase() === status ? '' : 'none';
  }});
}}
function expandAll() {{
  document.querySelectorAll('.test-card').forEach(c => c.classList.add('expanded'));
}}
function collapseAll() {{
  document.querySelectorAll('.test-card').forEach(c => c.classList.remove('expanded'));
}}
// All cards start collapsed by default (removed auto-expand for failed tests)
</script>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)
