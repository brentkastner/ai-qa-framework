"""Test plan data structures produced by the planner."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Action(BaseModel):
    action_type: str  # navigate, click, fill, select, hover, scroll, wait, screenshot, keyboard
    selector: Optional[str] = None
    value: Optional[str] = None
    description: str = ""


class Assertion(BaseModel):
    assertion_type: str  # element_visible, element_hidden, text_contains, text_equals,
    # url_matches, screenshot_diff, element_count,
    # network_request_made, no_console_errors, response_status
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
