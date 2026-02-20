"""Test executor — runs test plans using Playwright."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path

from playwright.async_api import async_playwright

from src.ai.client import AIClient
from src.auth.smart_auth import authenticate_and_capture_state
from src.utils.browser_stealth import launch_stealth_browser, create_stealth_context
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
from src.url_utils import page_id_from_url

from .action_runner import resolve_dynamic_vars_for_test_case, run_action
from .assertion_checker import check_assertion, check_api_assertion
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
        """Execute a full test plan and return results.

        Each test runs in a fully isolated browser context. If auth is
        configured, the session state (cookies + localStorage) is captured
        once and injected into each test's context via Playwright's
        storageState API — no repeated logins.
        """
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_time = time.time()
        total_tests = len(plan.test_cases)
        logger.info("Starting execution of plan %s (%d tests)",
                     plan.plan_id, total_tests)

        sorted_tests = sorted(plan.test_cases, key=lambda tc: tc.priority)

        async with async_playwright() as p:
            logger.debug("Launching stealth Chromium for test execution...")
            browser = await launch_stealth_browser(p)

            # Capture auth state once — will be injected into per-test contexts
            auth_storage_state: dict | None = None
            if self.config.auth:
                logger.info("Authenticating to capture session state...")
                auth_result, auth_storage_state = await authenticate_and_capture_state(
                    browser,
                    self.config.auth,
                    ai_client=self.ai_client,
                    viewport={"width": 1280, "height": 720},
                    user_agent=self.config.crawl.user_agent,
                )
                if auth_result.success:
                    method = auth_result.auth_flow.detection_method if auth_result.auth_flow else "unknown"
                    logger.info("Auth state captured successfully (method=%s)", method)
                else:
                    logger.error("Initial auth failed: %s", auth_result.error)

            # Run tests in parallel, bounded by max_parallel_contexts
            semaphore = asyncio.Semaphore(self.config.max_parallel_contexts)
            auth_lock = asyncio.Lock()
            auth_state: dict[str, dict | None] = {"storage": auth_storage_state}

            async def _run_one(index: int, tc: TestCase) -> TestResult:
                async with semaphore:
                    if tc.category not in self.config.categories:
                        logger.info("Skipping %s — category '%s' not in configured categories %s",
                                    tc.test_id, tc.category, self.config.categories)
                        return TestResult(
                            test_id=tc.test_id, test_name=tc.name,
                            description=tc.description, category=tc.category,
                            priority=tc.priority, target_page_id=tc.target_page_id,
                            coverage_signature=tc.coverage_signature,
                            result="skip",
                            failure_reason=f"Category '{tc.category}' not in configured categories",
                        )

                    elapsed = time.time() - start_time
                    if elapsed >= self.config.max_execution_time_seconds:
                        logger.warning("Time limit reached, skipping %s", tc.name)
                        return TestResult(
                            test_id=tc.test_id, test_name=tc.name,
                            description=tc.description, category=tc.category,
                            priority=tc.priority, target_page_id=tc.target_page_id,
                            coverage_signature=tc.coverage_signature,
                            result="skip", failure_reason="Time limit reached",
                        )

                    logger.info("Running test [%d/%d]: %s (%s)",
                                index + 1, total_tests, tc.name, tc.category)
                    logger.debug("  Test ID: %s | Page: %s | Timeout: %ds | requires_auth: %s",
                                 tc.test_id, tc.target_page_id, tc.timeout_seconds,
                                 tc.requires_auth)

                    storage = auth_state["storage"] if (tc.requires_auth and self.config.auth) else None
                    context = await create_stealth_context(
                        browser,
                        viewport={"width": 1280, "height": 720},
                        user_agent=self.config.crawl.user_agent,
                        storage_state=storage,
                    )
                    try:
                        result = await self._run_test(context, tc, baseline_dir)
                        logger.info("[%s] %s: %s (%.1fs)",
                                    result.result.upper(), tc.test_id, tc.name,
                                    result.duration_seconds or 0)

                        if self.config.auth and self._session_invalidated(result):
                            async with auth_lock:
                                logger.info("Session invalidated by %s, re-capturing auth state...",
                                            tc.test_id)
                                auth_result, new_state = await authenticate_and_capture_state(
                                    browser,
                                    self.config.auth,
                                    ai_client=self.ai_client,
                                    viewport={"width": 1280, "height": 720},
                                    user_agent=self.config.crawl.user_agent,
                                )
                                if auth_result.success:
                                    auth_state["storage"] = new_state
                                else:
                                    logger.error("Re-auth after session invalidation failed: %s",
                                                 auth_result.error)
                        return result
                    finally:
                        await context.close()

            test_results = list(await asyncio.gather(
                *(_run_one(i, tc) for i, tc in enumerate(sorted_tests))
            ))

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

    async def _run_api_test(self, context, tc: TestCase) -> TestResult:
        """Run an API test using Playwright's request context — no browser page opened.

        All actions must be api_get / api_post / api_put / api_delete / api_patch.
        Assertions operate on the HTTP response returned by the last action.
        """
        test_start = time.time()

        resolve_dynamic_vars_for_test_case(tc.preconditions + tc.steps)

        api = context.request
        step_results: list[StepResult] = []
        assertion_results_list: list[AssertionResultModel] = []
        last_response_data: dict = {}
        aborted = False

        for step_idx, action in enumerate(list(tc.preconditions) + list(tc.steps)):
            if aborted:
                step_results.append(StepResult(
                    step_index=step_idx, action_type=action.action_type,
                    selector=action.selector, value=action.value,
                    description=action.description, status="skip",
                    error_message="Skipped due to earlier step failure",
                ))
                continue
            try:
                resp_data = await _run_api_action(api, action)
                last_response_data = resp_data
                logger.debug("  API step %d: %s %s -> HTTP %d",
                             step_idx, action.action_type, action.selector,
                             resp_data.get("status", 0))
                step_results.append(StepResult(
                    step_index=step_idx, action_type=action.action_type,
                    selector=action.selector, value=action.value,
                    description=action.description, status="pass",
                ))
            except Exception as e:
                logger.warning("  API step %d failed: %s", step_idx, e)
                step_results.append(StepResult(
                    step_index=step_idx, action_type=action.action_type,
                    selector=action.selector, value=action.value,
                    description=action.description, status="fail",
                    error_message=str(e),
                ))
                aborted = True

        passed_count = 0
        failed_count = 0
        failure_reasons: list[str] = []

        for a_idx, assertion in enumerate(tc.assertions):
            result = check_api_assertion(assertion, last_response_data)
            ar = AssertionResultModel(
                assertion_type=assertion.assertion_type,
                selector=assertion.selector,
                expected_value=assertion.expected_value,
                description=assertion.description,
                passed=result.passed,
                message=result.message,
            )
            assertion_results_list.append(ar)
            if result.passed:
                passed_count += 1
                logger.debug("  API assertion %d/%d: PASSED — %s",
                             a_idx + 1, len(tc.assertions), result.message)
            else:
                failed_count += 1
                failure_reasons.append(f"{assertion.description or assertion.assertion_type}: {result.message}")
                logger.debug("  API assertion %d/%d: FAILED — %s",
                             a_idx + 1, len(tc.assertions), result.message)

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
            actual_page_id=tc.target_page_id,
            actual_url=last_response_data.get("url", ""),
            coverage_signature=tc.coverage_signature,
            result=test_result_status,
            duration_seconds=round(time.time() - test_start, 2),
            failure_reason="; ".join(failure_reasons) if failure_reasons else None,
            step_results=step_results,
            assertion_results=assertion_results_list,
            assertions_passed=passed_count,
            assertions_failed=failed_count,
            assertions_total=len(tc.assertions),
        )

    @staticmethod
    def _session_invalidated(result: TestResult) -> bool:
        """Check if a test likely invalidated the auth session (e.g. logout)."""
        if not result.evidence or not result.evidence.network_log:
            return False
        for entry in result.evidence.network_log:
            url = (entry.get("url") or "").lower()
            method = (entry.get("method") or "").upper()
            if method == "POST" and any(
                kw in url for kw in ("logout", "signout", "sign-out", "log-out")
            ):
                return True
        return False

    async def _run_test(
        self, context, test_case: TestCase, baseline_dir: Path | None,
    ) -> TestResult:
        """Run a single test case with full step/assertion detail recording."""
        if test_case.category == "api":
            return await self._run_api_test(context, test_case)

        tc = test_case
        test_start = time.time()
        evidence_dir = self.run_dir / "evidence" / tc.test_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Per-action selector timeout from config (distinct from overall test timeout)
        selector_timeout_ms = self.config.selector_timeout_seconds * 1000

        # Resolve dynamic variables (e.g. {{$timestamp}}) once for the entire
        # test case so preconditions and steps share the same values.
        resolve_dynamic_vars_for_test_case(tc.preconditions + tc.steps)

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
            if tc.preconditions:
                logger.debug("  Running %d preconditions...", len(tc.preconditions))
            for i, action in enumerate(tc.preconditions):
                logger.debug("  Precondition %d/%d: %s %s",
                             i + 1, len(tc.preconditions), action.action_type,
                             action.description or action.selector or "")
                step_screenshot = None
                try:
                    await run_action(page, action, timeout=selector_timeout_ms)
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
            logger.debug("  Running %d test steps...", len(tc.steps))
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

                logger.debug("  Step %d/%d: %s %s",
                             step_idx + 1, len(tc.steps), action.action_type,
                             action.description or action.selector or "")
                step_screenshot = None
                try:
                    await run_action(page, action, timeout=selector_timeout_ms)
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
                        logger.debug("  Step %d failed, attempting AI fallback (%d attempts remaining)...",
                                     step_idx + 1, fallback_handler.budget_remaining)
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
                                await run_action(page, retry_action, timeout=selector_timeout_ms, smart_resolve=False)
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
                                await run_action(page, fb_response.new_action, timeout=selector_timeout_ms, smart_resolve=False)
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

            # Capture the actual page the browser is on after steps execute.
            # This may differ from target_page_id when tests navigate (e.g. login → dashboard).
            # Only track valid HTTP(S) URLs — skip about:blank, data:, etc.
            current_url = page.url
            if current_url.startswith(("http://", "https://")):
                actual_page_id = page_id_from_url(current_url)
            else:
                actual_page_id = tc.target_page_id
            if actual_page_id != tc.target_page_id and tc.target_page_id:
                logger.info("Test navigated: target_page_id=%s, actual page=%s (%s)",
                            tc.target_page_id, actual_page_id, current_url)

            # === ASSERTIONS ===
            logger.debug("  Checking %d assertions...", len(tc.assertions))
            passed_count = 0
            failed_count = 0
            failure_reasons = []

            for a_idx, assertion in enumerate(tc.assertions):
                logger.debug("  Assertion %d/%d: %s — %s",
                             a_idx + 1, len(tc.assertions),
                             assertion.assertion_type,
                             assertion.description or assertion.selector or "")
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
                    logger.debug("  Assertion %d/%d: PASSED — %s",
                                 a_idx + 1, len(tc.assertions), result.message)
                else:
                    failed_count += 1
                    failure_reasons.append(f"{assertion.description}: {result.message}")
                    logger.debug("  Assertion %d/%d: FAILED — %s",
                                 a_idx + 1, len(tc.assertions), result.message)

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
                actual_page_id=actual_page_id,
                actual_url=current_url if current_url.startswith(("http://", "https://")) else "",
                coverage_signature=tc.coverage_signature,
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
                coverage_signature=tc.coverage_signature,
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


# ---------------------------------------------------------------------------
# Module-level helper for API actions (used by Executor._run_api_test)
# ---------------------------------------------------------------------------

async def _run_api_action(api, action) -> dict:
    """Execute a single API HTTP action and return parsed response data.

    Uses the Playwright APIRequestContext (``context.request``) which
    automatically shares cookies and auth state with the browser context.

    action.action_type  — one of: api_get, api_post, api_put, api_delete, api_patch
    action.selector     — full or relative URL
    action.value        — JSON-encoded request body (for POST / PUT / PATCH)
    """
    import json as _json

    url = action.selector or ""
    if not url:
        raise ValueError(
            f"API action '{action.action_type}' requires a URL in the selector field"
        )

    post_data = None
    if action.value:
        try:
            post_data = _json.loads(action.value)
        except (_json.JSONDecodeError, TypeError):
            post_data = action.value  # send as raw string

    # Use `json=` for dict payloads so Playwright sends Content-Type: application/json.
    # Raw strings are passed via `data=` as-is.
    def _kwargs(body):
        if isinstance(body, dict):
            return {"json": body}
        if body is not None:
            return {"data": body}
        return {}

    match action.action_type:
        case "api_get":
            response = await api.get(url)
        case "api_post":
            response = await api.post(url, **_kwargs(post_data))
        case "api_put":
            response = await api.put(url, **_kwargs(post_data))
        case "api_delete":
            response = await api.delete(url)
        case "api_patch":
            response = await api.patch(url, **_kwargs(post_data))
        case _:
            raise ValueError(f"Unknown API action type: {action.action_type}")

    body_text = await response.text()
    body_json = None
    try:
        body_json = await response.json()
    except Exception:
        pass

    return {
        "status": response.status,
        "headers": dict(response.headers),
        "body": body_text,
        "json": body_json,
        "url": url,
    }
