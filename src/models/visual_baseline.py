"""Visual baseline registry data structures."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BaselineEntry(BaseModel):
    page_id: str
    viewport_name: str
    viewport_width: int
    viewport_height: int
    image_path: str  # relative path from baselines_dir to the PNG
    captured_at: str  # ISO timestamp
    run_id: str
    image_hash: str  # SHA-256 hex digest


class VisualBaselineRegistry(BaseModel):
    target_url: str
    last_updated: str = ""
    baselines: dict[str, BaselineEntry] = Field(default_factory=dict)
    # key format: "{page_id}__{viewport_name}"
