"""Tests for the evidence collector module."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src.executor.evidence_collector import EvidenceCollector
from src.models.test_result import Evidence


class TestEvidenceCollectorInit:
    """Tests for EvidenceCollector initialization."""

    def test_creates_evidence_dir(self, tmp_path):
        evidence_dir = tmp_path / "evidence" / "tc_001"
        collector = EvidenceCollector(evidence_dir)
        assert evidence_dir.exists()

    def test_starts_empty(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")
        assert collector.console_logs == []
        assert collector.network_log == []
        assert collector._screenshot_count == 0


class TestSetupListeners:
    """Tests for console and network listener setup."""

    def test_captures_console_messages(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")

        # Simulate page with on() callbacks
        callbacks = {}
        mock_page = Mock()
        mock_page.on = Mock(side_effect=lambda event, cb: callbacks.update({event: cb}))

        collector.setup_listeners(mock_page)

        # Simulate console events
        msg = Mock()
        msg.type = "error"
        msg.text = "Uncaught TypeError: x is not a function"
        callbacks["console"](msg)

        msg2 = Mock()
        msg2.type = "warning"
        msg2.text = "Deprecated API usage"
        callbacks["console"](msg2)

        assert len(collector.console_logs) == 2
        assert "[error] Uncaught TypeError" in collector.console_logs[0]
        assert "[warning] Deprecated API" in collector.console_logs[1]

    def test_captures_network_responses(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")

        callbacks = {}
        mock_page = Mock()
        mock_page.on = Mock(side_effect=lambda event, cb: callbacks.update({event: cb}))

        collector.setup_listeners(mock_page)

        # Simulate network response
        resp = Mock()
        resp.url = "https://example.com/api/data"
        resp.status = 200
        resp.request = Mock()
        resp.request.method = "GET"
        resp.request.resource_type = "xhr"
        callbacks["response"](resp)

        assert len(collector.network_log) == 1
        assert collector.network_log[0]["url"] == "https://example.com/api/data"
        assert collector.network_log[0]["status"] == 200
        assert collector.network_log[0]["method"] == "GET"


class TestTakeScreenshot:
    """Tests for screenshot capture."""

    @pytest.mark.asyncio
    async def test_screenshot_saves_to_disk(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        collector = EvidenceCollector(evidence_dir)

        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock()

        path = await collector.take_screenshot(mock_page, "step_0")

        assert path != ""
        assert "screenshot_step_0_1.png" in path
        mock_page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_screenshot_counter_increments(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock()

        path1 = await collector.take_screenshot(mock_page, "a")
        path2 = await collector.take_screenshot(mock_page, "b")

        assert "_1.png" in path1
        assert "_2.png" in path2

    @pytest.mark.asyncio
    async def test_screenshot_handles_failure(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(side_effect=RuntimeError("Browser closed"))

        path = await collector.take_screenshot(mock_page, "fail")

        assert path == ""

    @pytest.mark.asyncio
    async def test_screenshot_without_label(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock()

        path = await collector.take_screenshot(mock_page)

        assert "screenshot_1.png" in path


class TestCaptureDomSnapshot:
    """Tests for DOM snapshot capture."""

    @pytest.mark.asyncio
    async def test_dom_snapshot_saves(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        collector = EvidenceCollector(evidence_dir)

        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Hello</body></html>")

        path = await collector.capture_dom_snapshot(mock_page)

        assert path != ""
        assert Path(path).exists()
        assert Path(path).read_text() == "<html><body>Hello</body></html>"

    @pytest.mark.asyncio
    async def test_dom_snapshot_handles_failure(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(side_effect=RuntimeError("Detached"))

        path = await collector.capture_dom_snapshot(mock_page)

        assert path == ""


class TestSaveLogs:
    """Tests for persisting logs to files."""

    def test_saves_console_log(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        collector = EvidenceCollector(evidence_dir)
        collector.console_logs = ["[error] Failed", "[info] Loaded"]

        collector.save_logs()

        console_path = evidence_dir / "console.log"
        assert console_path.exists()
        content = console_path.read_text()
        assert "[error] Failed" in content
        assert "[info] Loaded" in content

    def test_saves_network_log(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        collector = EvidenceCollector(evidence_dir)
        collector.network_log = [
            {"url": "https://example.com/api", "method": "GET", "status": 200},
        ]

        collector.save_logs()

        network_path = evidence_dir / "network.json"
        assert network_path.exists()
        data = json.loads(network_path.read_text())
        assert len(data) == 1
        assert data[0]["url"] == "https://example.com/api"

    def test_saves_empty_logs(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        collector = EvidenceCollector(evidence_dir)

        collector.save_logs()

        assert (evidence_dir / "console.log").exists()
        assert (evidence_dir / "network.json").exists()


class TestBuildEvidence:
    """Tests for building Evidence model."""

    def test_basic_evidence(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        collector = EvidenceCollector(evidence_dir)
        collector.console_logs = ["[error] Test error"]
        collector.network_log = [{"url": "https://example.com", "status": 200}]

        evidence = collector.build_evidence(screenshots=["/path/to/screenshot.png"])

        assert isinstance(evidence, Evidence)
        assert evidence.screenshots == ["/path/to/screenshot.png"]
        assert "[error] Test error" in evidence.console_logs
        assert len(evidence.network_log) == 1

    def test_dom_snapshot_included_when_exists(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "dom_snapshot.html").write_text("<html></html>")

        collector = EvidenceCollector(evidence_dir)
        evidence = collector.build_evidence(screenshots=[])

        assert evidence.dom_snapshot_path is not None
        assert "dom_snapshot.html" in evidence.dom_snapshot_path

    def test_dom_snapshot_none_when_missing(self, tmp_path):
        evidence_dir = tmp_path / "evidence"
        collector = EvidenceCollector(evidence_dir)
        evidence = collector.build_evidence(screenshots=[])

        assert evidence.dom_snapshot_path is None

    def test_empty_evidence(self, tmp_path):
        collector = EvidenceCollector(tmp_path / "evidence")
        evidence = collector.build_evidence(screenshots=[])

        assert evidence.screenshots == []
        assert evidence.console_logs == []
        assert evidence.network_log == []
