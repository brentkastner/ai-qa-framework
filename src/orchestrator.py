"""Pipeline orchestrator — coordinates crawl, plan, execute, and report stages."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from src.ai.client import AIClient, set_debug_dir
from src.coverage.gap_analyzer import analyze_gaps
from src.coverage.registry import CoverageRegistryManager
from src.coverage.scorer import calculate_coverage_summary
from src.coverage.visual_baseline_registry import VisualBaselineRegistryManager
from src.crawler.crawler import Crawler
from src.executor.executor import Executor
from src.models.config import FrameworkConfig
from src.models.site_model import SiteModel
from src.models.test_plan import TestPlan
from src.models.test_result import RunResult
from src.planner.planner import Planner
from src.reporter.reporter import Reporter

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the full QA pipeline."""

    def __init__(self, config: FrameworkConfig):
        self.config = config
        self.framework_dir = Path(".qa-framework")
        self.framework_dir.mkdir(exist_ok=True)
        self.runs_dir = Path("runs")
        self.runs_dir.mkdir(exist_ok=True)

        # Set up AI debug logging directory
        debug_dir = self.framework_dir / "debug"
        set_debug_dir(debug_dir)

        # Try to initialize AI client (optional — framework works without it)
        self.ai_client: AIClient | None = None
        try:
            self.ai_client = AIClient(
                model=config.ai_model,
                max_tokens=config.ai_max_planning_tokens,
            )
        except EnvironmentError as e:
            logger.warning("AI client unavailable: %s. Running in fallback mode.", e)

        self.registry_manager = CoverageRegistryManager(
            registry_path=self.framework_dir / "coverage" / "registry.json",
            target_url=config.target_url,
            history_retention=config.history_retention_runs,
        )

        self.visual_baseline_manager = VisualBaselineRegistryManager(
            registry_path=self.framework_dir / "visual_baselines" / "registry.json",
            baselines_dir=self.framework_dir / "visual_baselines",
            target_url=config.target_url,
        )

    def run_full_pipeline(self) -> dict:
        """Execute the complete crawl → plan → execute → report pipeline."""
        return asyncio.run(self._run_pipeline())

    async def _run_pipeline(self) -> dict:
        start = time.time()
        logger.info("=== Starting full QA pipeline for %s ===", self.config.target_url)

        # Stage 1: Crawl
        logger.info("--- Stage 1: Crawl ---")
        stage_start = time.time()
        site_model = await self._crawl()
        self._save_site_model(site_model)
        logger.info("--- Stage 1 complete: %d pages discovered in %.1fs ---",
                     len(site_model.pages), time.time() - stage_start)

        # Stage 2: Plan
        logger.info("--- Stage 2: Plan ---")
        stage_start = time.time()
        plan = self._plan(site_model)
        self._save_plan(plan)
        logger.info("--- Stage 2 complete: %d test cases generated in %.1fs ---",
                     len(plan.test_cases), time.time() - stage_start)

        # Stage 3: Execute
        logger.info("--- Stage 3: Execute (%d tests) ---", len(plan.test_cases))
        stage_start = time.time()
        run_result = await self._execute(plan)
        self._save_run_result(run_result)
        logger.info("--- Stage 3 complete: %d passed, %d failed in %.1fs ---",
                     run_result.passed, run_result.failed, time.time() - stage_start)

        # Stage 4: Update coverage
        logger.info("--- Stage 4: Update Coverage ---")
        stage_start = time.time()
        logger.debug("Loading coverage registry...")
        registry = self.registry_manager.load()
        logger.debug("Updating registry with run results...")
        registry = self.registry_manager.update_from_run(registry, run_result, site_model=site_model)
        self.registry_manager.save(registry)
        logger.info("--- Stage 4 complete in %.1fs ---", time.time() - stage_start)

        # Stage 5: Report
        logger.info("--- Stage 5: Report ---")
        stage_start = time.time()
        previous_run = self._load_previous_run_result(run_result.run_id)
        reports = self._report(run_result, registry, previous_run=previous_run)
        logger.info("--- Stage 5 complete: %d reports generated in %.1fs ---",
                     len(reports), time.time() - stage_start)

        duration = time.time() - start
        logger.info("=== Pipeline complete in %.1fs ===", duration)

        return {
            "run_id": run_result.run_id,
            "duration": round(duration, 2),
            "results": {
                "total": run_result.total_tests,
                "passed": run_result.passed,
                "failed": run_result.failed,
                "skipped": run_result.skipped,
                "errors": run_result.errors,
            },
            "coverage": {
                "overall": registry.global_stats.overall_score,
                "categories": registry.global_stats.category_scores,
            },
            "reports": reports,
        }

    async def _crawl(self) -> SiteModel:
        site_model_dir = self.framework_dir / "site_model"
        crawler = Crawler(self.config, site_model_dir, ai_client=self.ai_client)
        return await crawler.crawl()

    def run_crawl_only(self) -> SiteModel:
        """Run only the crawl stage."""
        return asyncio.run(self._crawl())

    def _plan(self, site_model: SiteModel) -> TestPlan:
        logger.debug("Loading coverage registry for gap analysis...")
        registry = self.registry_manager.load()
        logger.debug("Analyzing coverage gaps (staleness=%d days)...",
                      self.config.staleness_threshold_days)
        gap_report = analyze_gaps(
            registry, site_model, self.config.staleness_threshold_days
        )

        planner = Planner(self.config, self.ai_client)
        return planner.generate_plan(site_model, registry, gap_report)

    def run_plan_only(self) -> TestPlan:
        """Run only the planning stage (requires existing site model)."""
        site_model = self._load_site_model()
        return self._plan(site_model)

    async def _execute(self, plan: TestPlan) -> RunResult:
        baseline_dir = self.framework_dir / "site_model" / "baselines"
        visual_registry = self.visual_baseline_manager.load()
        executor = Executor(
            self.config, self.ai_client, self.runs_dir,
            visual_registry=visual_registry,
            visual_registry_manager=self.visual_baseline_manager,
        )
        result = await executor.execute(plan, baseline_dir if baseline_dir.exists() else None)
        # Save any newly captured baselines
        self.visual_baseline_manager.save(visual_registry)
        return result

    def run_execute_only(self, plan: TestPlan) -> RunResult:
        """Run only the execution stage with a given plan."""
        return asyncio.run(self._execute(plan))

    def _report(
        self, run_result: RunResult, registry=None,
        previous_run: RunResult | None = None,
    ) -> dict[str, str]:
        reporter = Reporter(self.config, self.ai_client)
        return reporter.generate_reports(
            run_result, registry,
            previous_run=previous_run,
            output_dir=Path(self.config.report_output_dir),
        )

    def _save_site_model(self, model: SiteModel) -> None:
        path = self.framework_dir / "site_model" / "model.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Saving site model to %s", path)
        with open(path, "w") as f:
            json.dump(model.model_dump(), f, indent=2, default=str)

    def _load_site_model(self) -> SiteModel:
        path = self.framework_dir / "site_model" / "model.json"
        if not path.exists():
            raise FileNotFoundError("No site model found. Run 'qa-framework crawl' first.")
        with open(path) as f:
            data = json.load(f)
        return SiteModel(**data)

    def _save_plan(self, plan: TestPlan) -> None:
        path = self.framework_dir / "latest_plan.json"
        logger.debug("Saving test plan to %s", path)
        with open(path, "w") as f:
            json.dump(plan.model_dump(), f, indent=2, default=str)

    def _save_run_result(self, run_result: RunResult) -> None:
        """Persist RunResult to the run directory for future regression comparison."""
        path = self.runs_dir / run_result.run_id / "run_result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Saving run result to %s", path)
        with open(path, "w") as f:
            json.dump(run_result.model_dump(), f, indent=2, default=str)

    def _load_previous_run_result(self, current_run_id: str) -> RunResult | None:
        """Load the most recent previous RunResult from existing JSON reports."""
        report_dir = Path(self.config.report_output_dir)
        if not report_dir.exists():
            return None

        report_files = sorted(
            report_dir.glob("report_run_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for report_path in report_files:
            try:
                with open(report_path) as f:
                    data = json.load(f)
                if data.get("run_id") == current_run_id:
                    continue
                return RunResult.model_validate(data)
            except Exception as e:
                logger.debug("Could not load previous run from %s: %s", report_path, e)
                continue

        return None

    def get_coverage_summary(self) -> str:
        """Get a human-readable coverage summary."""
        registry = self.registry_manager.load()
        return calculate_coverage_summary(registry)

    def get_coverage_gaps(self) -> str:
        """Get coverage gap analysis."""
        registry = self.registry_manager.load()
        site_model = self._load_site_model()
        gaps = analyze_gaps(registry, site_model, self.config.staleness_threshold_days)
        return json.dumps(gaps.model_dump(), indent=2, default=str)

    def reset_coverage(self) -> None:
        """Reset the coverage registry."""
        path = self.framework_dir / "coverage" / "registry.json"
        if path.exists():
            path.unlink()
        logger.info("Coverage registry reset")
