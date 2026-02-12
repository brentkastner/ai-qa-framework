"""Coverage gap analyzer — identifies untested and under-tested areas."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from src.models.coverage import CoverageGapReport, CoverageRegistry
from src.models.site_model import SiteModel

logger = logging.getLogger(__name__)


def analyze_gaps(
    registry: CoverageRegistry,
    site_model: SiteModel,
    staleness_days: int = 7,
    low_coverage_threshold: float = 0.5,
) -> CoverageGapReport:
    """Analyze coverage gaps based on the registry and site model."""
    now = datetime.utcnow()
    staleness_cutoff = now - timedelta(days=staleness_days)

    untested_pages = []
    stale_pages = []
    low_coverage_areas = []
    recent_failures = []

    # Check each page from the site model
    for page in site_model.pages:
        pid = page.page_id

        if pid not in registry.pages:
            untested_pages.append(pid)
            continue

        page_cov = registry.pages[pid]

        # Check staleness
        if page_cov.last_tested:
            try:
                last = datetime.fromisoformat(page_cov.last_tested.replace("Z", "+00:00")).replace(tzinfo=None)
                if last < staleness_cutoff:
                    stale_pages.append(pid)
            except ValueError:
                stale_pages.append(pid)
        else:
            stale_pages.append(pid)

        # Check low coverage
        for cat_name, cat_cov in page_cov.categories.items():
            if cat_cov.coverage_score < low_coverage_threshold:
                low_coverage_areas.append((pid, cat_name, cat_cov.coverage_score))

        # Check recent failures
        for cat_cov in page_cov.categories.values():
            for sig in cat_cov.signatures_tested:
                if sig.last_result == "fail":
                    recent_failures.append((pid, sig.signature))

    # Generate suggested focus areas
    suggested_focus = []
    if untested_pages:
        suggested_focus.append(f"Test {len(untested_pages)} untested pages")
    if recent_failures:
        suggested_focus.append(f"Re-test {len(recent_failures)} recent failures")
    if stale_pages:
        suggested_focus.append(f"Refresh {len(stale_pages)} stale pages")
    if low_coverage_areas:
        suggested_focus.append(f"Improve {len(low_coverage_areas)} low-coverage areas")

    report = CoverageGapReport(
        untested_pages=untested_pages,
        stale_pages=stale_pages,
        low_coverage_areas=low_coverage_areas,
        recent_failures=recent_failures,
        suggested_focus=suggested_focus,
    )

    logger.info(
        "Gap analysis: %d untested, %d stale, %d low-coverage, %d failures",
        len(untested_pages), len(stale_pages),
        len(low_coverage_areas), len(recent_failures),
    )
    return report
