"""Tests for configuration models."""

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.config import (
    AuthConfig,
    CrawlConfig,
    FrameworkConfig,
    ViewportConfig,
)


class TestViewportConfig:
    """Tests for ViewportConfig model."""

    def test_default_values(self):
        """Test ViewportConfig has correct default values."""
        config = ViewportConfig()
        assert config.width == 1280
        assert config.height == 720
        assert config.name == "desktop"

    def test_custom_values(self):
        """Test ViewportConfig accepts custom values."""
        config = ViewportConfig(width=375, height=812, name="mobile")
        assert config.width == 375
        assert config.height == 812
        assert config.name == "mobile"

    def test_serialization(self):
        """Test ViewportConfig can be serialized."""
        config = ViewportConfig(width=768, height=1024, name="tablet")
        data = config.model_dump()
        assert data == {"width": 768, "height": 1024, "name": "tablet"}


class TestCrawlConfig:
    """Tests for CrawlConfig model."""

    def test_default_values(self):
        """Test CrawlConfig has correct default values."""
        config = CrawlConfig()
        assert config.target_url == ""
        assert config.max_pages == 10
        assert config.max_depth == 5
        assert config.include_patterns == []
        assert config.exclude_patterns == []
        assert config.auth_credentials is None
        assert config.auth_url is None
        assert config.wait_for_idle is True
        assert isinstance(config.viewport, ViewportConfig)
        assert config.user_agent is None

    def test_custom_patterns(self):
        """Test CrawlConfig with custom include/exclude patterns."""
        config = CrawlConfig(
            include_patterns=["*/products/*", "*/catalog/*"],
            exclude_patterns=["*/admin/*", "*/private/*"],
        )
        assert len(config.include_patterns) == 2
        assert len(config.exclude_patterns) == 2

    def test_custom_viewport(self):
        """Test CrawlConfig with custom viewport."""
        viewport = ViewportConfig(width=1920, height=1080, name="large")
        config = CrawlConfig(viewport=viewport)
        assert config.viewport.width == 1920
        assert config.viewport.name == "large"


class TestAuthConfig:
    """Tests for AuthConfig model."""

    def test_required_fields(self):
        """Test AuthConfig requires login_url, username, password."""
        with pytest.raises(ValidationError):
            AuthConfig()

        with pytest.raises(ValidationError):
            AuthConfig(login_url="https://example.com")

    def test_valid_config(self):
        """Test AuthConfig with valid values."""
        config = AuthConfig(
            login_url="https://example.com/login",
            username="test@example.com",
            password="secret123",
        )
        assert config.login_url == "https://example.com/login"
        assert config.username == "test@example.com"
        assert config.password == "secret123"

    def test_default_selectors_empty_for_auto_detect(self):
        """Test AuthConfig defaults to empty selectors (triggers auto-detection)."""
        config = AuthConfig(
            login_url="https://example.com/login",
            username="user",
            password="pass",
        )
        assert config.username_selector == ""
        assert config.password_selector == ""
        assert config.submit_selector == ""
        assert config.auto_detect is True
        assert config.llm_fallback is True

    def test_env_password_resolution(self):
        """Test password can be resolved from environment variable."""
        os.environ["TEST_PASSWORD"] = "secret_from_env"
        try:
            config = AuthConfig(
                login_url="https://example.com/login",
                username="user",
                password="env:TEST_PASSWORD",
            )
            assert config.password == "secret_from_env"
        finally:
            del os.environ["TEST_PASSWORD"]

    def test_env_password_missing(self):
        """Test error when environment variable is not set."""
        with pytest.raises(ValidationError, match="Environment variable.*not set"):
            AuthConfig(
                login_url="https://example.com/login",
                username="user",
                password="env:NONEXISTENT_VAR",
            )


class TestFrameworkConfig:
    """Tests for FrameworkConfig model."""

    def test_required_fields(self):
        """Test FrameworkConfig requires target_url."""
        with pytest.raises(ValidationError):
            FrameworkConfig()

    def test_minimal_config(self):
        """Test FrameworkConfig with minimal required fields."""
        config = FrameworkConfig(target_url="https://example.com")
        assert config.target_url == "https://example.com"
        assert config.auth is None
        assert isinstance(config.crawl, CrawlConfig)

    def test_default_values(self):
        """Test FrameworkConfig has correct default values."""
        config = FrameworkConfig(target_url="https://example.com")
        assert config.categories == ["functional", "visual", "security"]
        assert config.max_tests_per_run == 20
        assert config.max_execution_time_seconds == 1800
        assert config.max_parallel_contexts == 3
        assert config.ai_model == "claude-opus-4-6"
        assert config.ai_max_fallback_calls_per_test == 3
        assert config.ai_max_planning_tokens == 32000
        assert config.staleness_threshold_days == 7
        assert config.history_retention_runs == 20
        assert config.visual_diff_tolerance == 0.05
        assert len(config.viewports) == 3
        assert len(config.security_xss_payloads) == 5
        assert config.security_max_probe_depth == 2
        assert config.report_formats == ["html", "json"]
        assert config.report_output_dir == "./qa-reports"
        assert config.capture_video is False

    def test_custom_categories(self):
        """Test FrameworkConfig with custom categories."""
        config = FrameworkConfig(
            target_url="https://example.com",
            categories=["functional", "performance"],
        )
        assert config.categories == ["functional", "performance"]

    def test_custom_ai_settings(self):
        """Test FrameworkConfig with custom AI settings."""
        config = FrameworkConfig(
            target_url="https://example.com",
            ai_model="claude-opus-4-6",
            ai_max_planning_tokens=16000,
        )
        assert config.ai_model == "claude-opus-4-6"
        assert config.ai_max_planning_tokens == 16000

    def test_custom_viewports(self):
        """Test FrameworkConfig with custom viewports."""
        viewports = [
            ViewportConfig(width=1920, height=1080, name="large"),
            ViewportConfig(width=1024, height=768, name="medium"),
        ]
        config = FrameworkConfig(
            target_url="https://example.com",
            viewports=viewports,
        )
        assert len(config.viewports) == 2
        assert config.viewports[0].name == "large"

    def test_post_init_sets_crawl_target(self):
        """Test model_post_init sets crawl.target_url if not provided."""
        config = FrameworkConfig(target_url="https://example.com")
        assert config.crawl.target_url == "https://example.com"

    def test_post_init_preserves_crawl_target(self):
        """Test model_post_init preserves crawl.target_url if provided."""
        crawl = CrawlConfig(target_url="https://different.com")
        config = FrameworkConfig(
            target_url="https://example.com",
            crawl=crawl,
        )
        assert config.crawl.target_url == "https://different.com"

    def test_with_auth(self):
        """Test FrameworkConfig with authentication."""
        auth = AuthConfig(
            login_url="https://example.com/login",
            username="test@example.com",
            password="secret",
        )
        config = FrameworkConfig(
            target_url="https://example.com",
            auth=auth,
        )
        assert config.auth is not None
        assert config.auth.username == "test@example.com"

    def test_with_hints(self):
        """Test FrameworkConfig with hints."""
        config = FrameworkConfig(
            target_url="https://example.com",
            hints=["Use unique vault names", "Login after creation"],
        )
        assert len(config.hints) == 2
        assert "vault" in config.hints[0].lower()


class TestFrameworkConfigFileOperations:
    """Tests for FrameworkConfig file load/save operations."""

    def test_load_valid_config(self, tmp_path: Path):
        """Test loading config from valid JSON file."""
        config_data = {
            "target_url": "https://example.com",
            "categories": ["functional"],
            "max_tests_per_run": 50,
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        config = FrameworkConfig.load(config_file)
        assert config.target_url == "https://example.com"
        assert config.categories == ["functional"]
        assert config.max_tests_per_run == 50

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test loading config from nonexistent file raises error."""
        config_file = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            FrameworkConfig.load(config_file)

    def test_save_config(self, tmp_path: Path):
        """Test saving config to JSON file."""
        config = FrameworkConfig(
            target_url="https://example.com",
            max_tests_per_run=25,
        )
        config_file = tmp_path / "saved-config.json"
        config.save(config_file)

        assert config_file.exists()
        with open(config_file) as f:
            data = json.load(f)
        assert data["target_url"] == "https://example.com"
        assert data["max_tests_per_run"] == 25

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        """Test saving config creates parent directories."""
        config = FrameworkConfig(target_url="https://example.com")
        config_file = tmp_path / "subdir" / "config.json"
        config.save(config_file)

        assert config_file.exists()
        assert config_file.parent.exists()

    def test_round_trip(self, tmp_path: Path):
        """Test saving and loading config produces equivalent object."""
        original = FrameworkConfig(
            target_url="https://example.com",
            categories=["functional", "visual"],
            max_tests_per_run=75,
            visual_diff_tolerance=0.15,
            hints=["Test hint"],
        )
        config_file = tmp_path / "config.json"
        original.save(config_file)
        loaded = FrameworkConfig.load(config_file)

        assert loaded.target_url == original.target_url
        assert loaded.categories == original.categories
        assert loaded.max_tests_per_run == original.max_tests_per_run
        assert loaded.visual_diff_tolerance == original.visual_diff_tolerance
        assert loaded.hints == original.hints
