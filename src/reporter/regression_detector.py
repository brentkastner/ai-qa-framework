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
    """Compare two runs and find tests that regressed (pass -> fail).

    Matches tests by coverage_signature first (stable across runs),
    falling back to test_name for tests without a signature.
    """
    # Build lookup keyed by coverage_signature (preferred) and test_name (fallback)
    prev_by_sig: dict[str, object] = {}
    prev_by_name: dict[str, object] = {}
    for r in previous.test_results:
        if r.coverage_signature:
            prev_by_sig[r.coverage_signature] = r
        prev_by_name[r.test_name] = r

    regressions = []

    for result in current.test_results:
        # Try matching by coverage_signature first, then by test_name
        prev = None
        if result.coverage_signature:
            prev = prev_by_sig.get(result.coverage_signature)
        if prev is None:
            prev = prev_by_name.get(result.test_name)

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
