"""Configuration models for the QA framework."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ViewportConfig(BaseModel):
    width: int = 1280
    height: int = 720
    name: str = "desktop"


class CrawlConfig(BaseModel):
    target_url: str = ""
    max_pages: int = 50
    max_depth: int = 5
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    auth_credentials: Optional[dict] = None
    auth_url: Optional[str] = None
    wait_for_idle: bool = True
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    user_agent: Optional[str] = None


class AuthConfig(BaseModel):
    login_url: str
    username: str
    password: str
    username_selector: str = "input[name='username'], input[type='email']"
    password_selector: str = "input[name='password'], input[type='password']"
    submit_selector: str = "button[type='submit']"
    success_indicator: str = ""

    @field_validator("password", mode="before")
    @classmethod
    def resolve_env_password(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("env:"):
            env_var = v[4:]
            resolved = os.environ.get(env_var)
            if resolved is None:
                raise ValueError(f"Environment variable '{env_var}' not set")
            return resolved
        return v


class FrameworkConfig(BaseModel):
    # Target
    target_url: str

    # Authentication
    auth: Optional[AuthConfig] = None

    # Crawl settings
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)

    # Test categories
    categories: list[str] = Field(
        default_factory=lambda: ["functional", "visual", "security"]
    )

    # Execution limits
    max_tests_per_run: int = 100
    max_execution_time_seconds: int = 1800
    max_parallel_contexts: int = 3

    # AI settings
    ai_model: str = "claude-opus-4-6"
    ai_max_fallback_calls_per_test: int = 3
    ai_max_planning_tokens: int = 32000  # Increased to support large test plans

    # Coverage settings
    staleness_threshold_days: int = 7
    history_retention_runs: int = 20

    # Visual testing
    visual_diff_tolerance: float = 0.05
    viewports: list[ViewportConfig] = Field(
        default_factory=lambda: [
            ViewportConfig(width=1280, height=720, name="desktop"),
            ViewportConfig(width=768, height=1024, name="tablet"),
            ViewportConfig(width=375, height=812, name="mobile"),
        ]
    )

    # Security testing
    security_xss_payloads: list[str] = Field(
        default_factory=lambda: [
            '<script>alert(1)</script>',
            '"><img src=x onerror=alert(1)>',
            "javascript:alert(1)",
            "'-alert(1)-'",
            '<svg onload=alert(1)>',
        ]
    )
    security_max_probe_depth: int = 2

    # Reporting
    report_formats: list[str] = Field(default_factory=lambda: ["html", "json"])
    report_output_dir: str = "./qa-reports"
    capture_video: bool = False

    # Scope
    include_url_patterns: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(default_factory=list)

    # Hints
    hints: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        if not self.crawl.target_url:
            self.crawl.target_url = self.target_url

    @classmethod
    def load(cls, path: str | Path) -> "FrameworkConfig":
        """Load config from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    def save(self, path: str | Path) -> None:
        """Save config to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)
