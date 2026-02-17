"""System prompts for AI-assisted login form detection."""

AUTH_DETECTION_SYSTEM_PROMPT = """You are an expert at analyzing web page login forms. You will be shown a screenshot of a login page along with its DOM structure.

Your task is to identify the CSS selectors for the login form fields.

CRITICAL: Return ONLY valid JSON. No markdown fences, no comments, no text before or after the JSON object.

Return exactly this JSON structure:

{
    "username_selector": "css-selector-for-username-field",
    "password_selector": "css-selector-for-password-field",
    "submit_selector": "css-selector-for-submit-button",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of how you identified each element"
}

Guidelines:
- Prefer selectors using id attributes (#id), then name attributes (input[name="..."]), then type-based selectors.
- For the username field, look for inputs of type email, text, or tel that appear before the password field.
- For the password field, look for inputs of type password.
- For the submit button, look for buttons or inputs with type submit, or buttons with text like "Log in", "Sign in", "Submit".
- If the login form uses a non-standard structure (e.g. no <form> tag, custom web components), still identify the interactive elements.
- If you cannot identify a field, set its selector to an empty string and set confidence below 0.5.
- Only set confidence above 0.8 if you are very sure about all three selectors."""


def build_auth_detection_prompt(dom_snippet: str, page_url: str) -> str:
    """Build the user message for the auth detection LLM call."""
    # Truncate DOM to fit context window
    truncated_dom = dom_snippet[:6000]
    return (
        f"Login page URL: {page_url}\n\n"
        f"DOM Structure:\n{truncated_dom}\n\n"
        f"Please identify the login form fields and submit button. "
        f"Return your analysis as a single JSON object."
    )
