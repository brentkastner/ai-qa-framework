"""AI-driven test plan generation."""

from __future__ import annotations

import json
import logging
import time
import uuid

from src.ai.client import AIClient
from src.ai.prompts.planning import PLANNING_SYSTEM_PROMPT, build_planning_prompt
from src.models.config import FrameworkConfig
from src.models.coverage import CoverageGapReport, CoverageRegistry
from src.models.site_model import SiteModel
from src.models.test_plan import Action, Assertion, TestCase, TestPlan

from .schema_validator import validate_test_plan

logger = logging.getLogger(__name__)

# Well-known placeholder tokens for credential injection.
# The LLM is instructed to use these in Action.value fields;
# _inject_credentials() replaces them with real config values after parsing.
AUTH_PLACEHOLDER_USERNAME = "{{auth_username}}"
AUTH_PLACEHOLDER_PASSWORD = "{{auth_password}}"
AUTH_PLACEHOLDER_LOGIN_URL = "{{auth_login_url}}"


class Planner:
    """Generates test plans using AI analysis of the site model and coverage gaps."""

    def __init__(self, config: FrameworkConfig, ai_client: AIClient):
        self.config = config
        self.ai_client = ai_client

    def generate_plan(
        self,
        site_model: SiteModel,
        coverage_registry: CoverageRegistry | None = None,
        gap_report: CoverageGapReport | None = None,
    ) -> TestPlan:
        """Generate a test plan from the site model and coverage data."""
        logger.info("Generating test plan for %s", site_model.base_url)

        # Build a summarized site model (to fit in context window)
        logger.debug("Summarizing site model (%d pages, %d API endpoints)...",
                      len(site_model.pages), len(site_model.api_endpoints))
        site_summary = self._summarize_site_model(site_model)
        logger.debug("Site summary: %d chars", len(site_summary))

        # Build coverage gaps summary
        gaps_summary = "{}"
        if gap_report:
            logger.debug("Building coverage gaps summary...")
            gaps_summary = gap_report.model_dump_json(indent=2)

        # Build config summary
        config_summary = (
            f"Categories: {', '.join(self.config.categories)}\n"
            f"Max tests: {self.config.max_tests_per_run}\n"
            f"Visual diff tolerance: {self.config.visual_diff_tolerance}\n"
            f"Viewports: {json.dumps([v.model_dump() for v in self.config.viewports])}\n"
        )

        # Build the prompt
        logger.debug("Building planning prompt (categories: %s, max_tests: %d)...",
                      ', '.join(self.config.categories), self.config.max_tests_per_run)
        user_message = build_planning_prompt(
            site_model_json=site_summary,
            coverage_gaps_json=gaps_summary,
            config_summary=config_summary,
            hints=self.config.hints,
            max_tests=self.config.max_tests_per_run,
        )
        logger.debug("Planning prompt built: %d chars", len(user_message))

        # Call AI
        try:
            logger.info("Requesting AI-generated test plan...")
            plan_data = self.ai_client.complete_json(
                system_prompt=PLANNING_SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=self.config.ai_max_planning_tokens,
            )
            logger.debug("AI returned plan data with %d test cases",
                          len(plan_data.get("test_cases", [])))
        except Exception as e:
            logger.error("AI planning failed: %s. Generating fallback plan.", e)
            return self._inject_credentials(self._generate_fallback_plan(site_model))

        # Parse and validate
        try:
            logger.debug("Parsing AI plan response...")
            plan = self._parse_plan(plan_data, site_model)
            logger.debug("Validating test plan...")
            errors = validate_test_plan(plan)
            if errors:
                logger.warning("Plan validation warnings: %s", errors)
                # Filter out invalid test cases
                plan.test_cases = [
                    tc for tc in plan.test_cases
                    if not any(tc.test_id in err for err in errors)
                ]
            # Inject real credentials in place of placeholder tokens
            plan = self._inject_credentials(plan)
            logger.info("Generated plan with %d test cases", len(plan.test_cases))
            return plan
        except Exception as e:
            logger.error("Failed to parse AI plan: %s. Using fallback.", e)
            return self._inject_credentials(self._generate_fallback_plan(site_model))

    def _summarize_site_model(self, site_model: SiteModel) -> str:
        """Create a condensed version of the site model for the AI prompt."""
        summary = {
            "base_url": site_model.base_url,
            "pages": [],
            "api_endpoints_count": len(site_model.api_endpoints),
            "has_auth": site_model.auth_flow is not None,
        }

        for page in site_model.pages[:30]:  # Limit pages
            page_summary = {
                "page_id": page.page_id,
                "url": page.url,
                "page_type": page.page_type,
                "title": page.title,
                "auth_required": page.auth_required,
                "interactive_elements_count": sum(1 for e in page.elements if e.is_interactive),
                "forms": [
                    {
                        "form_id": f.form_id,
                        "method": f.method,
                        "fields": [
                            {"name": ff.name, "type": ff.field_type, "required": ff.required}
                            for ff in f.fields
                        ],
                        "submit_selector": f.submit_selector,
                    }
                    for f in page.forms
                ],
                "key_elements": [
                    {
                        "selector": e.selector,
                        "type": e.element_type,
                        "text": e.text_content[:50],
                    }
                    for e in page.elements[:20]
                    if e.is_interactive
                ],
            }
            summary["pages"].append(page_summary)

        return json.dumps(summary, indent=2)

    def _parse_plan(self, data: dict, site_model: SiteModel) -> TestPlan:
        """Parse raw AI output into a TestPlan model."""
        plan_id = data.get("plan_id", f"plan_{uuid.uuid4().hex[:8]}")
        generated_at = data.get("generated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ"))

        test_cases = []
        for tc_data in data.get("test_cases", []):
            try:
                preconditions = [Action(**a) for a in tc_data.get("preconditions", [])]
                steps = [Action(**a) for a in tc_data.get("steps", [])]
                assertions = [Assertion(**a) for a in tc_data.get("assertions", [])]

                tc = TestCase(
                    test_id=tc_data.get("test_id", f"tc_{uuid.uuid4().hex[:6]}"),
                    name=tc_data.get("name", "Unnamed test"),
                    description=tc_data.get("description", ""),
                    category=tc_data.get("category", "functional"),
                    priority=tc_data.get("priority", 3),
                    target_page_id=tc_data.get("target_page_id", ""),
                    coverage_signature=tc_data.get("coverage_signature", ""),
                    requires_auth=tc_data.get("requires_auth", True),
                    preconditions=preconditions,
                    steps=steps,
                    assertions=assertions,
                    timeout_seconds=tc_data.get("timeout_seconds", 30),
                )
                test_cases.append(tc)
            except Exception as e:
                logger.warning("Skipping invalid test case: %s", e)

        return TestPlan(
            plan_id=plan_id,
            generated_at=generated_at,
            target_url=site_model.base_url,
            test_cases=test_cases,
            estimated_duration_seconds=data.get("estimated_duration_seconds", len(test_cases) * 15),
            coverage_intent=data.get("coverage_intent", {}),
        )

    def _generate_fallback_plan(self, site_model: SiteModel) -> TestPlan:
        """Generate a basic test plan without AI when API is unavailable."""
        logger.info("Generating fallback plan (no AI)")
        test_cases = []
        tc_num = 0

        for page in site_model.pages:
            # Basic navigation test for each page
            tc_num += 1
            test_cases.append(TestCase(
                test_id=f"tc_fallback_{tc_num:03d}",
                name=f"Navigate to {page.title or page.url}",
                description=f"Verify {page.url} loads successfully",
                category="functional",
                priority=3,
                target_page_id=page.page_id,
                coverage_signature=f"navigate_{page.page_id}",
                steps=[Action(action_type="navigate", value=page.url, description=f"Go to {page.url}")],
                assertions=[
                    Assertion(assertion_type="url_matches", expected_value=page.url, description="URL loaded"),
                    Assertion(assertion_type="no_console_errors", description="No console errors"),
                ],
            ))

            # Visual baseline test
            if "visual" in self.config.categories:
                tc_num += 1
                test_cases.append(TestCase(
                    test_id=f"tc_fallback_{tc_num:03d}",
                    name=f"Visual check: {page.title or page.url}",
                    category="visual",
                    priority=4,
                    target_page_id=page.page_id,
                    coverage_signature=f"visual_{page.page_id}",
                    steps=[
                        Action(action_type="navigate", value=page.url, description=f"Go to {page.url}"),
                        Action(action_type="screenshot", description="Capture page"),
                    ],
                    assertions=[
                        Assertion(
                            assertion_type="screenshot_diff",
                            tolerance=self.config.visual_diff_tolerance,
                            description="Compare against baseline",
                        ),
                    ],
                ))

            # Form tests
            for form in page.forms:
                tc_num += 1
                steps = [
                    Action(action_type="navigate", value=page.url, description=f"Go to {page.url}"),
                ]
                for field in form.fields:
                    if field.field_type in ("text", "email", "password", "textarea"):
                        val = _test_value_for_type(field.field_type, field.name)
                        steps.append(Action(
                            action_type="fill", selector=field.selector,
                            value=val, description=f"Fill {field.name}",
                        ))
                    elif field.field_type == "select" and field.options:
                        steps.append(Action(
                            action_type="select", selector=field.selector,
                            value=field.options[0], description=f"Select {field.name}",
                        ))
                    elif field.field_type == "checkbox":
                        steps.append(Action(
                            action_type="click", selector=field.selector,
                            description=f"Check {field.name}",
                        ))

                if form.submit_selector:
                    steps.append(Action(
                        action_type="click", selector=form.submit_selector,
                        description="Submit form",
                    ))

                test_cases.append(TestCase(
                    test_id=f"tc_fallback_{tc_num:03d}",
                    name=f"Submit form on {page.title or page.url}",
                    category="functional",
                    priority=2,
                    target_page_id=page.page_id,
                    coverage_signature=f"form_submit_{form.form_id}",
                    steps=steps,
                    assertions=[Assertion(
                        assertion_type="no_console_errors",
                        description="No errors after submission",
                    )],
                ))

        return TestPlan(
            plan_id=f"plan_fallback_{uuid.uuid4().hex[:8]}",
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            target_url=site_model.base_url,
            test_cases=test_cases[:self.config.max_tests_per_run],
            estimated_duration_seconds=len(test_cases) * 10,
        )

    @staticmethod
    def _has_auth_placeholders(tc: TestCase) -> bool:
        """Check if a test case contains any unresolved auth placeholder tokens."""
        tokens = (AUTH_PLACEHOLDER_USERNAME, AUTH_PLACEHOLDER_PASSWORD, AUTH_PLACEHOLDER_LOGIN_URL)
        for action in tc.preconditions + tc.steps:
            if action.value and any(t in action.value for t in tokens):
                return True
        for assertion in tc.assertions:
            if assertion.expected_value and any(t in assertion.expected_value for t in tokens):
                return True
        return False

    def _inject_credentials(self, plan: TestPlan) -> TestPlan:
        """Replace auth placeholder tokens in the plan with real credentials.

        Walks all Action.value fields in preconditions and steps, and
        Assertion.expected_value fields, substituting well-known placeholder
        tokens with actual credentials from self.config.auth.

        When auth is not configured, any test cases that still contain
        auth placeholders are removed from the plan as a safety net.
        """
        auth = self.config.auth
        if not auth:
            original_count = len(plan.test_cases)
            plan.test_cases = [
                tc for tc in plan.test_cases
                if not self._has_auth_placeholders(tc)
            ]
            removed = original_count - len(plan.test_cases)
            if removed:
                logger.info(
                    "Removed %d test case(s) with auth placeholders (no auth configured)",
                    removed,
                )
            return plan

        substitutions = {
            AUTH_PLACEHOLDER_USERNAME: auth.username,
            AUTH_PLACEHOLDER_PASSWORD: auth.password,
            AUTH_PLACEHOLDER_LOGIN_URL: auth.login_url,
        }

        sub_count = 0

        for tc in plan.test_cases:
            for action in tc.preconditions + tc.steps:
                if action.value:
                    new_value = action.value
                    for token, real_value in substitutions.items():
                        if token in new_value:
                            new_value = new_value.replace(token, real_value)
                    if new_value != action.value:
                        masked = new_value
                        if auth.password in masked:
                            masked = masked.replace(auth.password, "***")
                        logger.debug(
                            "Credential injection [%s]: '%s' -> '%s'",
                            tc.test_id, action.value, masked,
                        )
                        action.value = new_value
                        sub_count += 1

            for assertion in tc.assertions:
                if assertion.expected_value:
                    new_ev = assertion.expected_value
                    for token, real_value in substitutions.items():
                        if token in new_ev:
                            new_ev = new_ev.replace(token, real_value)
                    if new_ev != assertion.expected_value:
                        masked = new_ev
                        if auth.password in masked:
                            masked = masked.replace(auth.password, "***")
                        logger.debug(
                            "Credential injection [%s assertion]: '%s' -> '%s'",
                            tc.test_id, assertion.expected_value, masked,
                        )
                        assertion.expected_value = new_ev
                        sub_count += 1

        if sub_count > 0:
            logger.info("Injected credentials into %d action/assertion fields", sub_count)
        else:
            logger.debug("No credential placeholders found in plan")

        return plan


def _test_value_for_type(field_type: str, name: str) -> str:
    """Generate realistic test data based on field type/name."""
    name_lower = name.lower()
    if field_type == "email" or "email" in name_lower:
        return "test@example.com"
    if field_type == "password" or "password" in name_lower:
        return "TestP@ssw0rd123"
    if "phone" in name_lower or "tel" in name_lower:
        return "+1-555-000-1234"
    if "name" in name_lower:
        return "Test User"
    if "url" in name_lower or "website" in name_lower:
        return "https://example.com"
    if "zip" in name_lower or "postal" in name_lower:
        return "90210"
    return "Test input value"
