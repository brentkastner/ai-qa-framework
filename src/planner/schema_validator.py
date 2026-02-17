"""Test plan JSON schema validation."""

from __future__ import annotations

import logging

from src.models.test_plan import TestPlan

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"functional", "visual", "security"}
VALID_ACTION_TYPES = {
    "navigate", "click", "fill", "select", "hover",
    "scroll", "wait", "screenshot", "keyboard",
}
VALID_ASSERTION_TYPES = {
    "element_visible", "element_hidden", "text_contains", "text_equals",
    "text_matches", "url_matches", "screenshot_diff", "element_count",
    "network_request_made", "no_console_errors", "response_status",
    "ai_evaluate", "page_title_contains", "page_loaded",
}


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

        # At least one step
        if not tc.steps:
            errors.append(f"{tc.test_id}: no steps defined")

        # Validate actions
        for i, action in enumerate(tc.preconditions + tc.steps):
            if action.action_type not in VALID_ACTION_TYPES:
                errors.append(
                    f"{tc.test_id} step {i}: invalid action_type '{action.action_type}'"
                )
            # Actions that need a selector
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

    return errors
