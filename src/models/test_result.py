"""Test result data structures produced by the executor."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    screenshots: list[str] = Field(default_factory=list)  # file paths
    console_logs: list[str] = Field(default_factory=list)
    network_log: list[dict[str, Any]] = Field(default_factory=list)
    dom_snapshot_path: Optional[str] = None
    video_path: Optional[str] = None


class FallbackRecord(BaseModel):
    step_index: int
    original_selector: str = ""
    decision: str = ""  # retry, skip, abort, adapt
    new_selector: Optional[str] = None
    reasoning: str = ""


class StepResult(BaseModel):
    """Result of executing a single test step."""
    step_index: int
    action_type: str
    selector: Optional[str] = None
    value: Optional[str] = None
    description: str = ""
    status: str = "pass"  # pass, fail, skip
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None


class AssertionResult(BaseModel):
    """Result of evaluating a single assertion."""
    assertion_type: str
    selector: Optional[str] = None
    expected_value: Optional[str] = None
    description: str = ""
    passed: bool = False
    actual_value: Optional[str] = None
    message: str = ""


class TestResult(BaseModel):
    test_id: str
    test_name: str
    description: str = ""
    category: str
    priority: int = 3
    target_page_id: str = ""
    actual_page_id: str = ""  # page_id derived from browser URL after steps execute
    actual_url: str = ""  # the browser URL after steps execute
    coverage_signature: str = ""
    result: str  # pass, fail, skip, error
    duration_seconds: float = 0.0
    failure_reason: Optional[str] = None
    evidence: Evidence = Field(default_factory=Evidence)
    fallback_records: list[FallbackRecord] = Field(default_factory=list)
    # Detailed plan info
    precondition_results: list[StepResult] = Field(default_factory=list)
    step_results: list[StepResult] = Field(default_factory=list)
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    assertions_passed: int = 0
    assertions_failed: int = 0
    assertions_total: int = 0


class RunResult(BaseModel):
    run_id: str
    plan_id: str
    started_at: str
    completed_at: str
    target_url: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    test_results: list[TestResult] = Field(default_factory=list)
    ai_summary: str = ""
