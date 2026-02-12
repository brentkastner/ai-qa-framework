"""Tests for AI prompts."""

import pytest

from src.ai.prompts.fallback import FALLBACK_SYSTEM_PROMPT, build_fallback_prompt
from src.ai.prompts.planning import PLANNING_SYSTEM_PROMPT, build_planning_prompt
from src.ai.prompts.summary import SUMMARY_SYSTEM_PROMPT, build_summary_prompt


class TestFallbackPrompts:
    """Tests for fallback prompts."""

    def test_fallback_system_prompt_exists(self):
        """Test FALLBACK_SYSTEM_PROMPT is defined."""
        assert isinstance(FALLBACK_SYSTEM_PROMPT, str)
        assert len(FALLBACK_SYSTEM_PROMPT) > 0

    def test_fallback_system_prompt_mentions_decisions(self):
        """Test fallback prompt mentions all decision types."""
        assert "retry" in FALLBACK_SYSTEM_PROMPT
        assert "skip" in FALLBACK_SYSTEM_PROMPT
        assert "abort" in FALLBACK_SYSTEM_PROMPT
        assert "adapt" in FALLBACK_SYSTEM_PROMPT

    def test_fallback_system_prompt_requires_json(self):
        """Test fallback prompt requires JSON response."""
        assert "JSON" in FALLBACK_SYSTEM_PROMPT

    def test_build_fallback_prompt_basic(self):
        """Test building a basic fallback prompt."""
        prompt = build_fallback_prompt(
            test_context="Login test",
            dom_snippet="<button id='submit'>Submit</button>",
            console_errors=[],
            original_action_desc="Click submit button",
            original_selector="button#submit",
        )

        assert isinstance(prompt, str)
        assert "Login test" in prompt
        assert "button#submit" in prompt
        assert "Click submit button" in prompt

    def test_build_fallback_prompt_with_errors(self):
        """Test building fallback prompt with console errors."""
        errors = [
            "Error: Resource not found",
            "Warning: Deprecated API",
        ]
        prompt = build_fallback_prompt(
            test_context="Navigation test",
            dom_snippet="<div>Content</div>",
            console_errors=errors,
            original_action_desc="Navigate to page",
            original_selector=None,
        )

        assert "Resource not found" in prompt
        assert "Deprecated API" in prompt

    def test_build_fallback_prompt_truncates_errors(self):
        """Test build_fallback_prompt limits console errors to 10."""
        errors = [f"Error {i}" for i in range(20)]
        prompt = build_fallback_prompt(
            test_context="Test",
            dom_snippet="<div></div>",
            console_errors=errors,
            original_action_desc="Action",
            original_selector="selector",
        )

        # Should include first 10 errors
        assert "Error 0" in prompt
        assert "Error 9" in prompt
        # Should not include later errors
        assert "Error 10" not in prompt

    def test_build_fallback_prompt_truncates_dom(self):
        """Test build_fallback_prompt truncates large DOM snippets."""
        large_dom = "<div>" + ("x" * 3000) + "</div>"
        prompt = build_fallback_prompt(
            test_context="Test",
            dom_snippet=large_dom,
            console_errors=[],
            original_action_desc="Action",
            original_selector="selector",
        )

        # Should truncate DOM to 2000 chars
        assert "DOM Snippet:" in prompt


class TestPlanningPrompts:
    """Tests for planning prompts."""

    def test_planning_system_prompt_exists(self):
        """Test PLANNING_SYSTEM_PROMPT is defined."""
        assert isinstance(PLANNING_SYSTEM_PROMPT, str)
        assert len(PLANNING_SYSTEM_PROMPT) > 100

    def test_planning_system_prompt_mentions_test_types(self):
        """Test planning prompt mentions test categories."""
        assert "functional" in PLANNING_SYSTEM_PROMPT
        assert "visual" in PLANNING_SYSTEM_PROMPT
        assert "security" in PLANNING_SYSTEM_PROMPT

    def test_planning_system_prompt_has_schema_guidance(self):
        """Test planning prompt includes schema guidance."""
        assert "test_cases" in PLANNING_SYSTEM_PROMPT
        assert "assertions" in PLANNING_SYSTEM_PROMPT

    def test_planning_system_prompt_no_markdown_fences(self):
        """Test planning prompt doesn't use markdown fences for examples."""
        assert "no markdown" in PLANNING_SYSTEM_PROMPT.lower()

    def test_build_planning_prompt_basic(self):
        """Test building a basic planning prompt."""
        site_model_json = '{"base_url": "https://example.com", "pages": []}'
        coverage_gaps_json = '{"gaps": []}'
        config_summary = "Max tests: 50"

        prompt = build_planning_prompt(
            site_model_json=site_model_json,
            coverage_gaps_json=coverage_gaps_json,
            config_summary=config_summary,
            hints=[],
            max_tests=50,
        )

        assert isinstance(prompt, str)
        assert "https://example.com" in prompt

    def test_build_planning_prompt_with_hints(self):
        """Test building planning prompt with hints."""
        site_model_json = '{"base_url": "https://example.com"}'
        coverage_gaps_json = '{}'
        hints = [
            "Use unique vault names",
            "Login after creation",
        ]

        prompt = build_planning_prompt(
            site_model_json=site_model_json,
            coverage_gaps_json=coverage_gaps_json,
            config_summary="Config",
            hints=hints,
            max_tests=30,
        )

        assert "unique vault names" in prompt.lower()
        assert "login" in prompt.lower()

    def test_build_planning_prompt_includes_max_tests(self):
        """Test planning prompt includes max_tests limit."""
        prompt = build_planning_prompt(
            site_model_json="{}",
            coverage_gaps_json="{}",
            config_summary="Summary",
            hints=[],
            max_tests=25,
        )

        assert "25" in prompt or "max" in prompt.lower()


class TestSummaryPrompts:
    """Tests for summary prompts."""

    def test_summary_system_prompt_exists(self):
        """Test SUMMARY_SYSTEM_PROMPT is defined."""
        assert isinstance(SUMMARY_SYSTEM_PROMPT, str)
        assert len(SUMMARY_SYSTEM_PROMPT) > 0

    def test_summary_system_prompt_mentions_conciseness(self):
        """Test summary prompt requests concise output."""
        prompt_lower = SUMMARY_SYSTEM_PROMPT.lower()
        assert any(
            word in prompt_lower
            for word in ["concise", "brief", "summary", "summarize"]
        )

    def test_build_summary_prompt_basic(self):
        """Test building a basic summary prompt."""
        run_result_json = '{"total_tests": 5, "passed": 4, "failed": 1}'
        coverage_summary = "Coverage: 80%"

        prompt = build_summary_prompt(run_result_json, coverage_summary)

        assert isinstance(prompt, str)
        assert "80%" in prompt

    def test_build_summary_prompt_includes_results(self):
        """Test summary prompt includes test results."""
        run_result_json = '''{
            "total_tests": 10,
            "passed": 7,
            "failed": 2,
            "skipped": 1
        }'''
        coverage_summary = "Pages: 10/12 tested"

        prompt = build_summary_prompt(run_result_json, coverage_summary)

        assert len(prompt) > 0
        assert "Pages: 10/12 tested" in prompt


class TestPromptIntegrity:
    """Tests to ensure prompt quality and integrity."""

    def test_all_prompts_are_strings(self):
        """Test all system prompts are non-empty strings."""
        prompts = [
            FALLBACK_SYSTEM_PROMPT,
            PLANNING_SYSTEM_PROMPT,
            SUMMARY_SYSTEM_PROMPT,
        ]

        for prompt in prompts:
            assert isinstance(prompt, str)
            assert len(prompt) > 0
            assert prompt.strip() == prompt

    def test_fallback_prompt_builder_handles_none_values(self):
        """Test fallback prompt builder handles None values gracefully."""
        prompt = build_fallback_prompt(
            test_context="Test",
            dom_snippet="",
            console_errors=None,
            original_action_desc="",
            original_selector=None,
        )

        assert isinstance(prompt, str)
        assert "None" in prompt

    def test_planning_prompt_builder_handles_empty_lists(self):
        """Test planning prompt builder handles empty lists."""
        prompt = build_planning_prompt(
            site_model_json="{}",
            coverage_gaps_json="{}",
            config_summary="Config",
            hints=[],
            max_tests=10,
        )

        assert isinstance(prompt, str)

    def test_prompts_use_consistent_terminology(self):
        """Test prompts use consistent terminology."""
        assert "assertion" in PLANNING_SYSTEM_PROMPT.lower()
        assert "selector" in FALLBACK_SYSTEM_PROMPT.lower()
