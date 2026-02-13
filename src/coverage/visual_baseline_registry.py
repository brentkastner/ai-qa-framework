"""Visual baseline registry — stores and manages screenshot baselines for visual diff testing."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path

from src.models.visual_baseline import BaselineEntry, VisualBaselineRegistry

logger = logging.getLogger(__name__)


class VisualBaselineRegistryManager:
    """Manages visual baseline images and their JSON registry."""

    def __init__(self, registry_path: Path, baselines_dir: Path, target_url: str):
        self.registry_path = registry_path
        self.baselines_dir = baselines_dir
        self.target_url = target_url

    def load(self) -> VisualBaselineRegistry:
        """Load registry from disk, or create a new one."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path) as f:
                    data = json.load(f)
                return VisualBaselineRegistry(**data)
            except Exception as e:
                logger.warning("Failed to load visual baseline registry: %s. Creating new.", e)
        return VisualBaselineRegistry(target_url=self.target_url)

    def save(self, registry: VisualBaselineRegistry) -> None:
        """Persist registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(self.registry_path, "w") as f:
            json.dump(registry.model_dump(), f, indent=2)
        logger.debug("Saved visual baseline registry to %s", self.registry_path)

    def _baseline_key(self, page_id: str, viewport_name: str) -> str:
        return f"{page_id}__{viewport_name}"

    def _image_dir(self, page_id: str) -> Path:
        return self.baselines_dir / "images" / page_id

    def _image_path(self, page_id: str, viewport_name: str) -> Path:
        return self._image_dir(page_id) / f"{viewport_name}.png"

    def get_baseline(self, registry: VisualBaselineRegistry, page_id: str, viewport_name: str) -> BaselineEntry | None:
        """Look up an existing baseline for a page+viewport combination."""
        key = self._baseline_key(page_id, viewport_name)
        entry = registry.baselines.get(key)
        if entry is None:
            return None
        # Verify the image file still exists
        abs_path = self.baselines_dir / entry.image_path
        if not abs_path.exists():
            logger.warning("Baseline image missing for %s: %s", key, abs_path)
            return None
        return entry

    def get_baseline_image_path(self, entry: BaselineEntry) -> Path:
        """Return the absolute path to a baseline image."""
        return self.baselines_dir / entry.image_path

    def store_baseline(
        self,
        registry: VisualBaselineRegistry,
        page_id: str,
        viewport_name: str,
        viewport_width: int,
        viewport_height: int,
        source_image_path: Path,
        run_id: str,
    ) -> BaselineEntry:
        """Copy a screenshot into the baselines directory and register it."""
        dest = self._image_path(page_id, viewport_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image_path, dest)

        # Compute hash of the stored image
        image_hash = hashlib.sha256(dest.read_bytes()).hexdigest()

        # Relative path from baselines_dir for portability
        rel_path = str(dest.relative_to(self.baselines_dir))

        entry = BaselineEntry(
            page_id=page_id,
            viewport_name=viewport_name,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            image_path=rel_path,
            captured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            run_id=run_id,
            image_hash=image_hash,
        )

        key = self._baseline_key(page_id, viewport_name)
        registry.baselines[key] = entry
        logger.info("Stored baseline for %s (%dx%d)", key, viewport_width, viewport_height)
        return entry
