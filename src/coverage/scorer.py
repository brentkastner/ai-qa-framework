"""Coverage score calculation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.models.coverage import CoverageRegistry

logger = logging.getLogger(__name__)


def calculate_coverage_summary(registry: CoverageRegistry, staleness_days: int = 7) -> str:
    """Generate a human-readable coverage summary."""
    stats = registry.global_stats
    lines = [
        f"Coverage Summary for {registry.target_url}",
        f"  Pages: {stats.pages_tested}/{stats.total_pages} tested",
        f"  Overall score: {stats.overall_score:.0%}",
    ]
    for cat, score in stats.category_scores.items():
        lines.append(f"  {cat.capitalize()}: {score:.0%}")
    if stats.regression_count > 0:
        lines.append(f"  Regressions: {stats.regression_count}")
    if stats.last_full_run:
        lines.append(f"  Last run: {stats.last_full_run}")
    return "\n".join(lines)
