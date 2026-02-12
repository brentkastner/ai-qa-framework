"""Evidence collector — captures screenshots, console logs, network data."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from playwright.async_api import Page

from src.models.test_result import Evidence

logger = logging.getLogger(__name__)


class EvidenceCollector:
    """Collects test execution evidence (screenshots, logs, network data)."""

    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.console_logs: list[str] = []
        self.network_log: list[dict] = []
        self._screenshot_count = 0

    def setup_listeners(self, page: Page) -> None:
        """Attach console and network listeners to a page."""
        page.on("console", lambda msg: self.console_logs.append(
            f"[{msg.type}] {msg.text}"
        ))
        page.on("response", lambda resp: self.network_log.append({
            "url": resp.url,
            "method": resp.request.method,
            "status": resp.status,
            "resource_type": resp.request.resource_type,
        }))

    async def take_screenshot(self, page: Page, label: str = "") -> str:
        """Capture a screenshot and return the file path."""
        self._screenshot_count += 1
        name = f"screenshot_{label}_{self._screenshot_count}.png" if label else f"screenshot_{self._screenshot_count}.png"
        path = self.evidence_dir / name
        try:
            await page.screenshot(path=str(path), full_page=False)
            return str(path)
        except Exception as e:
            logger.warning("Screenshot failed: %s", e)
            return ""

    async def capture_dom_snapshot(self, page: Page) -> str:
        """Save the current DOM state."""
        path = self.evidence_dir / "dom_snapshot.html"
        try:
            content = await page.content()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return str(path)
        except Exception as e:
            logger.warning("DOM snapshot failed: %s", e)
            return ""

    def save_logs(self) -> None:
        """Persist collected logs to files."""
        # Console logs
        console_path = self.evidence_dir / "console.log"
        with open(console_path, "w") as f:
            f.write("\n".join(self.console_logs))

        # Network log
        network_path = self.evidence_dir / "network.json"
        with open(network_path, "w") as f:
            json.dump(self.network_log, f, indent=2)

    def build_evidence(self, screenshots: list[str]) -> Evidence:
        """Build an Evidence model from collected data."""
        return Evidence(
            screenshots=screenshots,
            console_logs=self.console_logs,
            network_log=self.network_log,
            dom_snapshot_path=str(self.evidence_dir / "dom_snapshot.html")
            if (self.evidence_dir / "dom_snapshot.html").exists()
            else None,
        )
