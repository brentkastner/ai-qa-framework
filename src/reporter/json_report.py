"""JSON report output."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.test_result import RunResult
from .regression_detector import Regression


def generate_json_report(
    run_result: RunResult,
    regressions: list[Regression],
    output_path: Path,
) -> None:
    """Write a machine-readable JSON report."""
    report = run_result.model_dump()
    report["regressions"] = [
        {
            "test_name": r.test_name,
            "category": r.category,
            "previous_result": r.previous_result,
            "current_result": r.current_result,
            "failure_reason": r.failure_reason,
        }
        for r in regressions
    ]

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
