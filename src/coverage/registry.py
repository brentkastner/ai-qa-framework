"""Coverage registry — persists and manages test coverage state."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from src.models.coverage import (
    CategoryCoverage,
    CoverageRegistry,
    GlobalCoverageStats,
    PageCoverage,
    SignatureRecord,
    TestResultSummary,
)
from src.models.site_model import SiteModel
from src.models.test_result import RunResult, TestResult

logger = logging.getLogger(__name__)


class CoverageRegistryManager:
    """Manages the coverage registry JSON file."""

    def __init__(self, registry_path: Path, target_url: str, history_retention: int = 20):
        self.path = registry_path
        self.target_url = target_url
        self.history_retention = history_retention

    def load(self) -> CoverageRegistry:
        """Load registry from disk, or create a new one."""
        if self.path.exists():
            try:
                with open(self.path) as f:
                    data = json.load(f)
                return CoverageRegistry(**data)
            except Exception as e:
                logger.warning("Failed to load registry: %s. Creating new.", e)
        return CoverageRegistry(target_url=self.target_url)

    def save(self, registry: CoverageRegistry) -> None:
        """Persist registry to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        registry.last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(self.path, "w") as f:
            json.dump(registry.model_dump(), f, indent=2)
        logger.debug("Saved coverage registry to %s", self.path)

    def update_from_run(
        self, registry: CoverageRegistry, run_result: RunResult,
        site_model: SiteModel | None = None,
    ) -> CoverageRegistry:
        """Update coverage registry with results from a test run."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build a lookup from site model for page metadata
        page_lookup: dict[str, tuple[str, str]] = {}
        if site_model:
            for p in site_model.pages:
                page_lookup[p.page_id] = (p.url, p.page_type)

        for test_result in run_result.test_results:
            # Prefer actual_page_id (where the browser ended up) over target_page_id
            # (where the test plan said to start). This correctly attributes coverage
            # when tests navigate across pages (e.g. login → dashboard).
            page_id = (
                test_result.actual_page_id
                or test_result.target_page_id
                or test_result.test_id
            )
            category = test_result.category

            # Ensure page entry exists
            if page_id not in registry.pages:
                url, page_type = page_lookup.get(page_id, ("", ""))
                # Fall back to actual_url from test result for pages not in site model
                if not url and test_result.actual_url:
                    url = test_result.actual_url
                registry.pages[page_id] = PageCoverage(
                    page_id=page_id, url=url, page_type=page_type,
                )

            page_cov = registry.pages[page_id]
            page_cov.last_tested = now
            page_cov.test_count += 1

            # Ensure category entry exists
            if category not in page_cov.categories:
                page_cov.categories[category] = CategoryCoverage(category=category)

            cat_cov = page_cov.categories[category]
            cat_cov.last_tested = now

            # Update signature record
            sig = test_result.coverage_signature or test_result.test_name
            existing = None
            for sr in cat_cov.signatures_tested:
                if sr.signature == sig:
                    existing = sr
                    break

            summary = TestResultSummary(
                run_id=run_result.run_id,
                timestamp=now,
                result=test_result.result,
                duration_seconds=test_result.duration_seconds,
                failure_reason=test_result.failure_reason,
            )

            if existing:
                existing.last_tested = now
                existing.last_result = test_result.result
                existing.test_count += 1
                existing.history.append(summary)
                # Trim history
                if len(existing.history) > self.history_retention:
                    existing.history = existing.history[-self.history_retention:]
            else:
                cat_cov.signatures_tested.append(SignatureRecord(
                    signature=sig,
                    last_tested=now,
                    last_result=test_result.result,
                    test_count=1,
                    history=[summary],
                ))

        # Recalculate global stats
        self._recalculate_stats(registry)

        return registry

    def _recalculate_stats(self, registry: CoverageRegistry) -> None:
        """Recalculate global coverage statistics."""
        total_pages = len(registry.pages)
        pages_tested = sum(1 for p in registry.pages.values() if p.test_count > 0)

        category_scores: dict[str, float] = {}
        for page_cov in registry.pages.values():
            for cat_name, cat_cov in page_cov.categories.items():
                passed = sum(1 for s in cat_cov.signatures_tested if s.last_result == "pass")
                total = len(cat_cov.signatures_tested)
                cat_cov.coverage_score = passed / total if total > 0 else 0.0
                category_scores.setdefault(cat_name, 0.0)
                category_scores[cat_name] += cat_cov.coverage_score

        # Average category scores across pages
        for cat_name in category_scores:
            pages_with_cat = sum(
                1 for p in registry.pages.values() if cat_name in p.categories
            )
            if pages_with_cat > 0:
                category_scores[cat_name] /= pages_with_cat

        overall = sum(category_scores.values()) / len(category_scores) if category_scores else 0.0

        # Count regressions
        regression_count = 0
        for page_cov in registry.pages.values():
            for cat_cov in page_cov.categories.values():
                for sig in cat_cov.signatures_tested:
                    if len(sig.history) >= 2:
                        prev = sig.history[-2].result
                        curr = sig.history[-1].result
                        if prev == "pass" and curr == "fail":
                            regression_count += 1

        registry.global_stats = GlobalCoverageStats(
            total_pages=total_pages,
            pages_tested=pages_tested,
            overall_score=round(overall, 3),
            category_scores={k: round(v, 3) for k, v in category_scores.items()},
            last_full_run=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            regression_count=regression_count,
        )
