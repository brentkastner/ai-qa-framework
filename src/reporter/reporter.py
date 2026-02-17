"""Report generation orchestration."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.ai.client import AIClient
from src.ai.prompts.summary import SUMMARY_SYSTEM_PROMPT, build_summary_prompt
from src.coverage.scorer import calculate_coverage_summary
from src.models.config import FrameworkConfig
from src.models.coverage import CoverageRegistry
from src.models.test_result import RunResult

from .html_report import generate_html_report
from .json_report import generate_json_report
from .regression_detector import detect_regressions

logger = logging.getLogger(__name__)


class Reporter:
    """Generates reports from test results."""

    def __init__(self, config: FrameworkConfig, ai_client: AIClient | None = None):
        self.config = config
        self.ai_client = ai_client

    def generate_reports(
        self,
        run_result: RunResult,
        registry: CoverageRegistry | None = None,
        previous_run: RunResult | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, str]:
        """Generate all configured report formats. Returns format -> file path."""
        out_dir = output_dir or Path(self.config.report_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        generated = {}
        logger.debug("Report output directory: %s", out_dir)

        # Generate AI summary
        if self.ai_client and not run_result.ai_summary:
            logger.debug("Generating AI-powered test summary...")
            run_result.ai_summary = self._generate_summary(run_result, registry)

        # Detect regressions if we have a previous run
        regressions = []
        if previous_run:
            logger.debug("Detecting regressions against previous run...")
            regressions = detect_regressions(previous_run, run_result)
            logger.debug("Found %d regressions", len(regressions))

        if "html" in self.config.report_formats:
            path = out_dir / f"report_{run_result.run_id}.html"
            logger.debug("Generating HTML report...")
            generate_html_report(run_result, regressions, registry, path)
            generated["html"] = str(path)
            logger.info("HTML report: %s", path)

        if "json" in self.config.report_formats:
            path = out_dir / f"report_{run_result.run_id}.json"
            logger.debug("Generating JSON report...")
            generate_json_report(run_result, regressions, path)
            generated["json"] = str(path)
            logger.info("JSON report: %s", path)

        return generated

    def _generate_summary(
        self, run_result: RunResult, registry: CoverageRegistry | None
    ) -> str:
        """Generate an AI-powered natural language summary."""
        if not self.ai_client:
            return self._generate_basic_summary(run_result)

        try:
            # Summarize results for the prompt (limit size)
            results_summary = {
                "run_id": run_result.run_id,
                "target_url": run_result.target_url,
                "total": run_result.total_tests,
                "passed": run_result.passed,
                "failed": run_result.failed,
                "skipped": run_result.skipped,
                "errors": run_result.errors,
                "duration": run_result.duration_seconds,
                "failures": [
                    {"name": r.test_name, "category": r.category, "reason": r.failure_reason}
                    for r in run_result.test_results if r.result in ("fail", "error")
                ][:20],
            }

            coverage_text = ""
            if registry:
                coverage_text = calculate_coverage_summary(registry)

            summary = self.ai_client.complete(
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_message=build_summary_prompt(
                    json.dumps(results_summary, indent=2),
                    coverage_text,
                ),
                max_tokens=500,
            )
            return summary.strip()
        except Exception as e:
            logger.warning("AI summary generation failed: %s", e)
            return self._generate_basic_summary(run_result)

    def _generate_basic_summary(self, run_result: RunResult) -> str:
        """Generate a basic summary without AI."""
        parts = [
            f"Tested {run_result.target_url}: {run_result.total_tests} tests in {run_result.duration_seconds:.1f}s.",
            f"Results: {run_result.passed} passed, {run_result.failed} failed, "
            f"{run_result.skipped} skipped, {run_result.errors} errors.",
        ]
        failures = [r for r in run_result.test_results if r.result == "fail"]
        if failures:
            parts.append(f"Key failures: {', '.join(f.test_name for f in failures[:5])}")
        return " ".join(parts)
