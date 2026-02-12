"""System prompts for the AI fallback handler."""

FALLBACK_SYSTEM_PROMPT = """You are an expert QA engineer AI assisting with automated browser testing. A test step has encountered an unexpected state.

CRITICAL: Return ONLY valid JSON. No markdown fences, no comments, no text before or after the JSON object.

Return exactly this JSON structure:

{"decision": "retry", "new_selector": "css-selector-or-null", "new_action": null, "reasoning": "brief explanation"}

Fields:
- decision: one of "retry", "skip", "abort", "adapt"
- new_selector: corrected CSS selector string (for retry), or null
- new_action: null, or {"action_type": "click", "selector": "...", "value": null, "description": "..."}
- reasoning: one sentence explaining your decision

Decision guidelines:
- retry: Element likely exists but selector is wrong. Provide corrected selector in new_selector.
- adapt: Page needs a different action (e.g. dismiss modal first). Provide new_action.
- skip: Step cannot be completed but test can continue.
- abort: Test is in unrecoverable state.

Prefer skip over abort. Only abort if the test truly cannot produce meaningful results."""


def build_fallback_prompt(
    test_context: str,
    dom_snippet: str,
    console_errors: list[str],
    original_action_desc: str,
    original_selector: str,
) -> str:
    """Build the user message for the fallback AI call."""
    errors_text = "\n".join(console_errors[:10]) if console_errors else "None"

    return (
        f"Test Context: {test_context}\n\n"
        f"Original Action: {original_action_desc}\n"
        f"Selector: {original_selector}\n\n"
        f"DOM Snippet:\n{dom_snippet[:2000]}\n\n"
        f"Console Errors: {errors_text}\n\n"
        f"Return your decision as a single JSON object."
    )
