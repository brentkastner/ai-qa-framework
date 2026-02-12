"""System prompts for AI-generated report summaries."""

SUMMARY_SYSTEM_PROMPT = """You are an expert QA engineer AI. Given test execution results, produce a concise, actionable natural-language summary. Focus on:

1. Overall health: How many tests passed/failed/skipped
2. Key failures: What broke and likely root causes
3. Security findings: Any security issues discovered
4. Visual regressions: Any visual changes detected
5. Coverage trends: How coverage has changed
6. Recommendations: What should be investigated or fixed

Be concise but specific. Reference page names and test names where relevant. Write 3-8 sentences."""


def build_summary_prompt(run_results_json: str, coverage_summary: str) -> str:
    """Build the user message for the summary AI call."""
    return (
        f"## Test Run Results\n\n```json\n{run_results_json}\n```\n\n"
        f"## Coverage Summary\n\n{coverage_summary}\n\n"
        f"Generate a concise, actionable summary of these test results."
    )
