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

    def run_full_pipeline(self) -> dict:
        """Execute the complete crawl → plan → execute → report pipeline."""
        return asyncio.run(self._run_pipeline())

    async def _run_pipeline(self) -> dict:
        start = time.time()
        logger.info("=== Starting full QA pipeline for %s ===", self.config.target_url)

        # Stage 1: Crawl
        logger.info("--- Stage 1: Crawl ---")
        site_model = await self._crawl()
        self._save_site_model(site_model)

        # Stage 2: Plan
        logger.info("--- Stage 2: Plan ---")
        plan = self._plan(site_model)
        self._save_plan(plan)

        # Stage 3: Execute
        logger.info("--- Stage 3: Execute ---")
        run_result = await self._execute(plan)

        # Stage 4: Update coverage
        logger.info("--- Stage 4: Update Coverage ---")
        registry = self.registry_manager.load()
        registry = self.registry_manager.update_from_run(registry, run_result)
        self.registry_manager.save(registry)

        # Stage 5: Report
        logger.info("--- Stage 5: Report ---")
        reports = self._report(run_result, registry)

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
        crawler = Crawler(self.config, site_model_dir)
        return await crawler.crawl()

    def run_crawl_only(self) -> SiteModel:
        """Run only the crawl stage."""
        return asyncio.run(self._crawl())

    def _plan(self, site_model: SiteModel) -> TestPlan:
        registry = self.registry_manager.load()
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
        executor = Executor(self.config, self.ai_client, self.runs_dir)
        return await executor.execute(plan, baseline_dir if baseline_dir.exists() else None)

    def run_execute_only(self, plan: TestPlan) -> RunResult:
        """Run only the execution stage with a given plan."""
        return asyncio.run(self._execute(plan))

    def _report(
        self, run_result: RunResult, registry=None
    ) -> dict[str, str]:
        reporter = Reporter(self.config, self.ai_client)
        return reporter.generate_reports(
            run_result, registry,
            output_dir=Path(self.config.report_output_dir),
        )

    def _save_site_model(self, model: SiteModel) -> None:
        path = self.framework_dir / "site_model" / "model.json"
        path.parent.mkdir(parents=True, exist_ok=True)
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
        with open(path, "w") as f:
            json.dump(plan.model_dump(), f, indent=2, default=str)

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
