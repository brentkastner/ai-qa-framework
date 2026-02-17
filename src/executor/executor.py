"""Test executor — runs test plans using Playwright."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path

from playwright.async_api import async_playwright

from src.ai.client import AIClient
from src.auth.smart_auth import perform_smart_auth
from src.coverage.visual_baseline_registry import VisualBaselineRegistryManager
from src.models.config import FrameworkConfig
from src.models.test_plan import TestCase, TestPlan
from src.models.test_result import (
    AssertionResult as AssertionResultModel,
    RunResult,
    StepResult,
    TestResult,
)
from src.models.visual_baseline import VisualBaselineRegistry

from .action_runner import run_action
from .assertion_checker import check_assertion
from .evidence_collector import EvidenceCollector
from .fallback import FallbackHandler

logger = logging.getLogger(__name__)


class Executor:
    """Executes test plans against a live site using Playwright."""

    def __init__(
        self,
        config: FrameworkConfig,
        ai_client: AIClient | None,
        runs_dir: Path,
        visual_registry: VisualBaselineRegistry | None = None,
        visual_registry_manager: VisualBaselineRegistryManager | None = None,
    ):
        self.config = config
        self.ai_client = ai_client
        self.runs_dir = runs_dir
        self.run_id = f"run_{uuid.uuid4().hex[:8]}"
        self.run_dir = runs_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.visual_registry = visual_registry
        self.visual_registry_manager = visual_registry_manager

    async def execute(self, plan: TestPlan, baseline_dir: Path | None = None) -> RunResult:
        """Execute a full test plan and return results."""
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_time = time.time()
        logger.info("Starting execution of plan %s (%d tests)",
                     plan.plan_id, len(plan.test_cases))

        sorted_tests = sorted(plan.test_cases, key=lambda tc: tc.priority)

        page_groups: dict[str, list[TestCase]] = {}
        for tc in sorted_tests:
            key = tc.target_page_id or "ungrouped"
            page_groups.setdefault(key, []).append(tc)

        test_results: list[TestResult] = []
        remaining_time = self.config.max_execution_time_seconds

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 720})

            if self.config.auth:
                await self._authenticate(context)

            for group_key, tests in page_groups.items():
                if remaining_time <= 0:
                    for tc in tests:
                        test_results.append(TestResult(
                            test_id=tc.test_id, test_name=tc.name,
                            description=tc.description, category=tc.category,
                            priority=tc.priority, target_page_id=tc.target_page_id,
                            result="skip", failure_reason="Time limit reached",
                        ))
                    continue

                for tc in tests:
                    elapsed = time.time() - start_time
                    remaining_time = self.config.max_execution_time_seconds - elapsed
                    if remaining_time <= 0:
                        test_results.append(TestResult(
                            test_id=tc.test_id, test_name=tc.name,
                            description=tc.description, category=tc.category,
                            priority=tc.priority, target_page_id=tc.target_page_id,
                            result="skip", failure_reason="Time limit reached",
                        ))
                        continue

                    result = await self._run_test(context, tc, baseline_dir)
                    test_results.append(result)
                    logger.info("[%s] %s: %s", result.result.upper(), tc.test_id, tc.name)

            await browser.close()

        duration = time.time() - start_time
        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        run_result = RunResult(
            run_id=self.run_id,
            plan_id=plan.plan_id,
            started_at=started_at,
            completed_at=completed_at,
            target_url=plan.target_url,
            total_tests=len(test_results),
            passed=sum(1 for r in test_results if r.result == "pass"),
            failed=sum(1 for r in test_results if r.result == "fail"),
            skipped=sum(1 for r in test_results if r.result == "skip"),
            errors=sum(1 for r in test_results if r.result == "error"),
            duration_seconds=round(duration, 2),
            test_results=test_results,
        )

        logger.info(
            "Execution complete: %d passed, %d failed, %d skipped, %d errors (%.1fs)",
            run_result.passed, run_result.failed, run_result.skipped,
            run_result.errors, duration,
        )
        return run_result

    async def _authenticate(self, context) -> None:
        auth = self.config.auth
        if not auth:
            return
        result = await perform_smart_auth(context, auth, ai_client=self.ai_client)
        if result.success:
            method = result.auth_flow.detection_method if result.auth_flow else "unknown"
            logger.info("Executor auth successful (method=%s)", method)
        else:
            logger.error("Executor auth failed: %s", result.error)

    async def _run_test(
        self, context, test_case: TestCase, baseline_dir: Path | None,
    ) -> TestResult:
        """Run a single test case with full step/assertion detail recording."""
        tc = test_case
        test_start = time.time()
        evidence_dir = self.run_dir / "evidence" / tc.test_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        collector = EvidenceCollector(evidence_dir)
        fallback_handler = None
        if self.ai_client:
            fallback_handler = FallbackHandler(
                self.ai_client, self.config.ai_max_fallback_calls_per_test
            )

        screenshots = []
        fallback_records = []
        precondition_results = []
        step_results = []
        assertion_results_list = []

        page = await context.new_page()
        collector.setup_listeners(page)

        try:
            # === PRECONDITIONS ===
            for i, action in enumerate(tc.preconditions):
                step_screenshot = None
                try:
                    await run_action(page, action, timeout=tc.timeout_seconds * 1000)
                    step_screenshot = await collector.take_screenshot(page, f"precond_{i}")
                    if step_screenshot:
                        screenshots.append(step_screenshot)
                    precondition_results.append(StepResult(
                        step_index=i, action_type=action.action_type,
                        selector=action.selector, value=action.value,
                        description=action.description, status="pass",
                        screenshot_path=step_screenshot,
                    ))
                except Exception as e:
                    step_screenshot = await collector.take_screenshot(page, f"precond_{i}_fail")
                    if step_screenshot:
                        screenshots.append(step_screenshot)
                    precondition_results.append(StepResult(
                        step_index=i, action_type=action.action_type,
                        selector=action.selector, value=action.value,
                        description=action.description, status="fail",
                        error_message=str(e), screenshot_path=step_screenshot,
                    ))
                    logger.warning("Precondition %d failed: %s", i, e)

            # === TEST STEPS ===
            is_visual = tc.category == "visual"
            aborted = False
            for step_idx, action in enumerate(tc.steps):
                if aborted:
                    step_results.append(StepResult(
                        step_index=step_idx, action_type=action.action_type,
                        selector=action.selector, value=action.value,
                        description=action.description, status="skip",
                        error_message="Skipped due to earlier abort",
                    ))
                    continue

                step_screenshot = None
                try:
                    await run_action(page, action, timeout=tc.timeout_seconds * 1000)
                    # Skip step screenshots for visual tests — viewport shots are
                    # captured by the assertion checker and are more useful.
                    if not is_visual:
                        step_screenshot = await collector.take_screenshot(page, f"step_{step_idx}")
                        if step_screenshot:
                            screenshots.append(step_screenshot)
                    step_results.append(StepResult(
                        step_index=step_idx, action_type=action.action_type,
                        selector=action.selector, value=action.value,
                        description=action.description, status="pass",
                        screenshot_path=step_screenshot,
                    ))
                except Exception as e:
                    fail_screenshot = await collector.take_screenshot(page, f"step_{step_idx}_fail")
                    if fail_screenshot:
                        screenshots.append(fail_screenshot)

                    # Try AI fallback
                    recovered = False
                    if fallback_handler and fallback_handler.budget_remaining > 0:
                        dom = ""
                        try:
                            dom = await page.content()
                        except Exception:
                            pass

                        fb_response = fallback_handler.request_fallback(
                            test_context=f"Test: {tc.name}\nStep {step_idx}: {action.description}",
                            screenshot_path=fail_screenshot or "",
                            dom_snippet=dom[:3000],
                            console_errors=collector.console_logs[-5:],
                            original_action=action,
                        )
                        record = fallback_handler.to_record(step_idx, action.selector or "", fb_response)
                        fallback_records.append(record)

                        if fb_response.decision == "retry" and fb_response.new_selector:
                            retry_action = action.model_copy()
                            retry_action.selector = fb_response.new_selector
                            try:
                                await run_action(page, retry_action, timeout=tc.timeout_seconds * 1000)
                                retry_screenshot = await collector.take_screenshot(page, f"step_{step_idx}_retry")
                                if retry_screenshot:
                                    screenshots.append(retry_screenshot)
                                step_results.append(StepResult(
                                    step_index=step_idx, action_type=action.action_type,
                                    selector=fb_response.new_selector, value=action.value,
                                    description=f"{action.description} (retried with new selector)",
                                    status="pass", screenshot_path=retry_screenshot,
                                ))
                                recovered = True
                            except Exception:
                                pass
                        elif fb_response.decision == "adapt" and fb_response.new_action:
                            try:
                                await run_action(page, fb_response.new_action, timeout=tc.timeout_seconds * 1000)
                                adapt_screenshot = await collector.take_screenshot(page, f"step_{step_idx}_adapt")
                                if adapt_screenshot:
                                    screenshots.append(adapt_screenshot)
                                step_results.append(StepResult(
                                    step_index=step_idx, action_type=fb_response.new_action.action_type,
                                    selector=fb_response.new_action.selector,
                                    value=fb_response.new_action.value,
                                    description=f"{action.description} (adapted: {fb_response.reasoning})",
                                    status="pass", screenshot_path=adapt_screenshot,
                                ))
                                recovered = True
                            except Exception:
                                pass
                        elif fb_response.decision == "abort":
                            step_results.append(StepResult(
                                step_index=step_idx, action_type=action.action_type,
                                selector=action.selector, value=action.value,
                                description=action.description, status="fail",
                                error_message=f"Aborted: {fb_response.reasoning}",
                                screenshot_path=fail_screenshot,
                            ))
                            aborted = True
                            continue

                    if not recovered:
                        step_results.append(StepResult(
                            step_index=step_idx, action_type=action.action_type,
                            selector=action.selector, value=action.value,
                            description=action.description, status="fail",
                            error_message=str(e), screenshot_path=fail_screenshot,
                        ))

            # === ASSERTIONS ===
            passed_count = 0
            failed_count = 0
            failure_reasons = []

            for assertion in tc.assertions:
                result = await check_assertion(
                    page, assertion, evidence_dir, baseline_dir,
                    collector.console_logs, collector.network_log,
                    self.config, self.ai_client,
                    visual_registry=self.visual_registry,
                    visual_registry_manager=self.visual_registry_manager,
                    page_id=tc.target_page_id,
                    run_id=self.run_id,
                )
                ar = AssertionResultModel(
                    assertion_type=assertion.assertion_type,
                    selector=assertion.selector,
                    expected_value=assertion.expected_value,
                    description=assertion.description,
                    passed=result.passed,
                    message=result.message,
                )
                assertion_results_list.append(ar)

                # Collect viewport screenshots captured by screenshot_diff
                if result.screenshots:
                    screenshots.extend(result.screenshots)

                if result.passed:
                    passed_count += 1
                else:
                    failed_count += 1
                    failure_reasons.append(f"{assertion.description}: {result.message}")

            # Final screenshot (skip for visual tests — viewport shots already captured)
            if tc.category != "visual":
                s = await collector.take_screenshot(page, "final")
                if s:
                    screenshots.append(s)

            collector.save_logs()

            test_result_status = "pass" if failed_count == 0 and not aborted else "fail"
            if aborted and failed_count == 0:
                test_result_status = "error"

            return TestResult(
                test_id=tc.test_id,
                test_name=tc.name,
                description=tc.description,
                category=tc.category,
                priority=tc.priority,
                target_page_id=tc.target_page_id,
                result=test_result_status,
                duration_seconds=round(time.time() - test_start, 2),
                failure_reason="; ".join(failure_reasons) if failure_reasons else None,
                evidence=collector.build_evidence(screenshots),
                fallback_records=fallback_records,
                precondition_results=precondition_results,
                step_results=step_results,
                assertion_results=assertion_results_list,
                assertions_passed=passed_count,
                assertions_failed=failed_count,
                assertions_total=len(tc.assertions),
            )

        except Exception as e:
            logger.error("Test %s crashed: %s", tc.test_id, e)
            collector.save_logs()
            return TestResult(
                test_id=tc.test_id,
                test_name=tc.name,
                description=tc.description,
                category=tc.category,
                priority=tc.priority,
                target_page_id=tc.target_page_id,
                result="error",
                duration_seconds=round(time.time() - test_start, 2),
                failure_reason=str(e),
                evidence=collector.build_evidence(screenshots),
                fallback_records=fallback_records,
                precondition_results=precondition_results,
                step_results=step_results,
                assertion_results=assertion_results_list,
            )
        finally:
            await page.close()
