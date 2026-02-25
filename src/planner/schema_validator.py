"""Test plan JSON schema validation."""

from __future__ import annotations

import logging

from src.models.test_plan import TestPlan

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"functional", "visual", "security", "api"}
VALID_ACTION_TYPES = {
    "navigate", "click", "fill", "select", "hover",
    "scroll", "wait", "screenshot", "keyboard",
    "api_get", "api_post", "api_put", "api_delete", "api_patch",
}
API_ACTION_TYPES = {"api_get", "api_post", "api_put", "api_delete", "api_patch"}
BROWSER_ASSERTION_TYPES = {
    "element_visible", "element_hidden", "text_contains", "text_equals",
    "text_matches", "url_matches", "screenshot_diff", "element_count",
    "network_request_made", "no_console_errors", "ai_evaluate",
    "page_title_contains", "page_loaded",
}
API_ASSERTION_TYPES = {
    "response_status", "response_body_contains", "response_json_path", "response_header",
}
VALID_ASSERTION_TYPES = BROWSER_ASSERTION_TYPES | API_ASSERTION_TYPES


def validate_test_plan(plan: TestPlan) -> list[str]:
    """Validate a test plan and return a list of error messages."""
    errors = []

    if not plan.test_cases:
        errors.append("Test plan has no test cases")
        return errors

    seen_ids = set()
    for tc in plan.test_cases:
        # Unique IDs
        if tc.test_id in seen_ids:
            errors.append(f"Duplicate test_id: {tc.test_id}")
        seen_ids.add(tc.test_id)

        # Valid category
        if tc.category not in VALID_CATEGORIES:
            errors.append(f"{tc.test_id}: invalid category '{tc.category}'")

        # Priority range
        if not 1 <= tc.priority <= 5:
            errors.append(f"{tc.test_id}: priority must be 1-5, got {tc.priority}")

        # requires_auth must be a boolean
        if not isinstance(tc.requires_auth, bool):
            errors.append(f"{tc.test_id}: requires_auth must be a boolean, got {type(tc.requires_auth).__name__}")

        # Determine whether this is an API test by inspecting actions
        all_actions = tc.preconditions + tc.steps
        is_api_test = tc.category == "api" or any(a.action_type in API_ACTION_TYPES for a in all_actions)

        # At least one step (API tests may put their action in preconditions)
        if not tc.steps and not (is_api_test and tc.preconditions):
            errors.append(f"{tc.test_id}: no steps defined")

        # API tests: name must follow [METHOD] format
        if is_api_test and not tc.name.startswith("["):
            errors.append(
                f"{tc.test_id}: api test name must start with [METHOD] (e.g. '[GET] List users'), got '{tc.name}'"
            )

        # Validate actions
        for i, action in enumerate(all_actions):
            if action.action_type not in VALID_ACTION_TYPES:
                errors.append(
                    f"{tc.test_id} step {i}: invalid action_type '{action.action_type}'"
                )
            # API actions require a URL in selector
            if action.action_type in API_ACTION_TYPES and not action.selector:
                errors.append(
                    f"{tc.test_id} step {i}: {action.action_type} requires a URL in the selector field"
                )
            # Non-API actions that need a selector
            if action.action_type in ("click", "fill", "select", "hover") and not action.selector:
                errors.append(
                    f"{tc.test_id} step {i}: {action.action_type} requires a selector"
                )
            # Fill needs a value
            if action.action_type == "fill" and not action.value:
                errors.append(f"{tc.test_id} step {i}: fill requires a value")

        # Validate assertions
        for i, assertion in enumerate(tc.assertions):
            if assertion.assertion_type not in VALID_ASSERTION_TYPES:
                errors.append(
                    f"{tc.test_id} assertion {i}: invalid type '{assertion.assertion_type}'"
                )
            # API tests must not use browser assertions
            if is_api_test and assertion.assertion_type in BROWSER_ASSERTION_TYPES:
                errors.append(
                    f"{tc.test_id} assertion {i}: api test uses browser assertion '{assertion.assertion_type}' — use response_status, response_json_path, response_body_contains, or response_header"
                )

    return errors
