"""Test plan data structures produced by the planner."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Action(BaseModel):
    # Browser actions: navigate, click, fill, select, hover, scroll, wait, screenshot, keyboard
    # API actions (category="api" tests only): api_get, api_post, api_put, api_delete, api_patch
    #   selector = full endpoint URL; value = JSON-encoded request body (POST/PUT/PATCH)
    action_type: str
    selector: Optional[str] = None
    value: Optional[str] = None
    description: str = ""


class Assertion(BaseModel):
    # Browser assertions: element_visible, element_hidden, text_contains, text_equals,
    #   text_matches, url_matches, screenshot_diff, element_count,
    #   network_request_made, no_console_errors, response_status,
    #   ai_evaluate, page_title_contains, page_loaded
    # API assertions (category="api" tests only):
    #   response_status      — expected_value = HTTP status code string e.g. "200"
    #   response_body_contains — expected_value = substring to find in response body
    #   response_json_path   — selector = dot-notation path e.g. "data.id"; expected_value = expected substring
    #   response_header      — selector = header name; expected_value = expected substring in header value
    assertion_type: str
    selector: Optional[str] = None
    expected_value: Optional[str] = None
    tolerance: Optional[float] = None
    description: str = ""


class TestCase(BaseModel):
    test_id: str
    name: str
    description: str = ""
    category: str = "functional"  # functional, visual, security
    priority: int = 3  # 1 (critical) to 5 (low)
    target_page_id: str = ""
    coverage_signature: str = ""
    requires_auth: bool = True  # Whether this test needs an authenticated session
    preconditions: list[Action] = Field(default_factory=list)
    steps: list[Action] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    timeout_seconds: int = 30


class TestPlan(BaseModel):
    plan_id: str
    generated_at: str
    target_url: str
    test_cases: list[TestCase] = Field(default_factory=list)
    estimated_duration_seconds: int = 0
    coverage_intent: dict = Field(default_factory=dict)
