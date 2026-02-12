"""Coverage registry data structures."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TestResultSummary(BaseModel):
    run_id: str
    timestamp: str
    result: str
    duration_seconds: float = 0.0
    failure_reason: Optional[str] = None


class SignatureRecord(BaseModel):
    signature: str
    last_tested: str = ""
    last_result: str = ""
    test_count: int = 0
    history: list[TestResultSummary] = Field(default_factory=list)


class ElementCoverage(BaseModel):
    element_id: str
    tested: bool = False
    last_tested: Optional[str] = None
    test_count: int = 0


class CategoryCoverage(BaseModel):
    category: str
    signatures_tested: list[SignatureRecord] = Field(default_factory=list)
    coverage_score: float = 0.0
    last_tested: str = ""


class PageCoverage(BaseModel):
    page_id: str
    url: str
    page_type: str = ""
    categories: dict[str, CategoryCoverage] = Field(default_factory=dict)
    elements_tested: dict[str, ElementCoverage] = Field(default_factory=dict)
    last_tested: str = ""
    test_count: int = 0


class GlobalCoverageStats(BaseModel):
    total_pages: int = 0
    pages_tested: int = 0
    overall_score: float = 0.0
    category_scores: dict[str, float] = Field(default_factory=dict)
    last_full_run: str = ""
    regression_count: int = 0


class CoverageGapReport(BaseModel):
    untested_pages: list[str] = Field(default_factory=list)
    stale_pages: list[str] = Field(default_factory=list)
    low_coverage_areas: list[tuple[str, str, float]] = Field(default_factory=list)
    recent_failures: list[tuple[str, str]] = Field(default_factory=list)
    suggested_focus: list[str] = Field(default_factory=list)


class CoverageRegistry(BaseModel):
    target_url: str
    last_updated: str = ""
    pages: dict[str, PageCoverage] = Field(default_factory=dict)
    journeys: dict = Field(default_factory=dict)
    global_stats: GlobalCoverageStats = Field(default_factory=GlobalCoverageStats)
