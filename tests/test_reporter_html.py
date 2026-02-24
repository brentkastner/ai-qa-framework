"""Tests for HTML report generation — video section and flaky badge."""

import pytest

from src.models.test_result import Evidence, TestResult
from src.reporter.html_report import _build_test_card


def _make_test_result(**kwargs) -> TestResult:
    """Create a TestResult with sensible defaults for report testing."""
    defaults = {
        "test_id": "tc_001",
        "test_name": "Test Login Form",
        "description": "Verify login works",
        "category": "functional",
        "priority": 1,
        "result": "pass",
        "duration_seconds": 1.5,
        "assertions_passed": 1,
        "assertions_total": 1,
    }
    defaults.update(kwargs)
    return TestResult(**defaults)


class TestFlakyBadge:
    """Tests for the potentially flaky badge in test cards."""

    def test_card_shows_flaky_badge(self):
        """Flaky badge appears when potentially_flaky is True."""
        tr = _make_test_result(result="fail", potentially_flaky=True)
        card = _build_test_card(tr)
        assert "POTENTIALLY FLAKY" in card
        assert "badge flaky" in card

    def test_card_no_flaky_badge_when_false(self):
        """Flaky badge is absent for non-flaky tests."""
        tr = _make_test_result(result="fail")
        card = _build_test_card(tr)
        assert "POTENTIALLY FLAKY" not in card

    def test_card_no_flaky_badge_for_passing_test(self):
        """Passing tests never show flaky badge."""
        tr = _make_test_result(result="pass")
        card = _build_test_card(tr)
        assert "POTENTIALLY FLAKY" not in card

    def test_flaky_banner_content(self):
        """Flaky info banner explains the re-run behavior."""
        tr = _make_test_result(result="fail", potentially_flaky=True)
        card = _build_test_card(tr)
        assert "failed initially but passed on a video re-run" in card
        assert "flaky-banner" in card

    def test_no_flaky_banner_when_not_flaky(self):
        """No flaky banner for non-flaky tests."""
        tr = _make_test_result(result="fail", failure_reason="Element not found")
        card = _build_test_card(tr)
        assert "flaky-banner" not in card


class TestVideoSection:
    """Tests for video recording section in test cards."""

    def test_card_shows_video_section(self):
        """Video section appears when video_path is set."""
        tr = _make_test_result()
        tr.evidence.video_path = "/path/to/video.webm"
        card = _build_test_card(tr)
        assert "Video Recording" in card
        assert "<video" in card
        assert "video.webm" in card
        assert "file:///" in card

    def test_card_no_video_section_when_none(self):
        """No video section when video_path is None."""
        tr = _make_test_result()
        card = _build_test_card(tr)
        assert "Video Recording" not in card
        assert "<video" not in card

    def test_card_escapes_video_path(self):
        """Special characters in video path are HTML-escaped."""
        tr = _make_test_result()
        tr.evidence.video_path = '/path/with <special>&"chars/video.webm'
        card = _build_test_card(tr)
        # Angle brackets must be escaped
        assert "<special>" not in card
        assert "&lt;special&gt;" in card

    def test_video_has_controls(self):
        """Video element includes controls attribute for playback."""
        tr = _make_test_result()
        tr.evidence.video_path = "/path/to/recording.webm"
        card = _build_test_card(tr)
        assert 'controls' in card
        assert 'type="video/webm"' in card

    def test_video_section_with_flaky_badge(self):
        """Video section and flaky badge both appear together."""
        tr = _make_test_result(result="fail", potentially_flaky=True)
        tr.evidence.video_path = "/evidence/rerun/video.webm"
        card = _build_test_card(tr)
        assert "POTENTIALLY FLAKY" in card
        assert "Video Recording" in card
        assert "<video" in card
