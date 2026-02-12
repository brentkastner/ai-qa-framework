"""Regression detection — compares run results to find new failures."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.models.test_result import RunResult

logger = logging.getLogger(__name__)


@dataclass
class Regression:
    test_name: str
    category: str
    previous_result: str
    current_result: str
    failure_reason: str | None = None


def detect_regressions(previous: RunResult, current: RunResult) -> list[Regression]:
    """Compare two runs and find tests that regressed (pass -> fail)."""
    prev_map = {r.test_name: r for r in previous.test_results}
    regressions = []

    for result in current.test_results:
        prev = prev_map.get(result.test_name)
        if prev and prev.result == "pass" and result.result in ("fail", "error"):
            regressions.append(Regression(
                test_name=result.test_name,
                category=result.category,
                previous_result=prev.result,
                current_result=result.result,
                failure_reason=result.failure_reason,
            ))

    if regressions:
        logger.warning("Detected %d regressions", len(regressions))
    return regressions
