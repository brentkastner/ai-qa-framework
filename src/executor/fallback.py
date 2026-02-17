"""AI fallback handler — invoked when test execution hits unexpected states."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

from src.ai.client import AIClient
from src.ai.prompts.fallback import FALLBACK_SYSTEM_PROMPT, build_fallback_prompt
from src.models.test_plan import Action
from src.models.test_result import FallbackRecord

logger = logging.getLogger(__name__)


class FallbackResponse:
    def __init__(
        self,
        decision: str,
        new_selector: Optional[str] = None,
        new_action: Optional[Action] = None,
        reasoning: str = "",
    ):
        self.decision = decision
        self.new_selector = new_selector
        self.new_action = new_action
        self.reasoning = reasoning


class FallbackHandler:
    """Handles AI-assisted recovery when test steps fail."""

    def __init__(self, ai_client: AIClient, max_calls_per_test: int = 3):
        self.ai_client = ai_client
        self.max_calls = max_calls_per_test
        self._call_count = 0

    def reset(self) -> None:
        self._call_count = 0

    @property
    def budget_remaining(self) -> int:
        return max(0, self.max_calls - self._call_count)

    def request_fallback(
        self,
        test_context: str,
        screenshot_path: str,
        dom_snippet: str,
        console_errors: list[str],
        original_action: Action,
    ) -> FallbackResponse:
        """Request AI guidance for a failed step."""
        if self._call_count >= self.max_calls:
            logger.warning("Fallback budget exhausted")
            return FallbackResponse(decision="abort", reasoning="Fallback budget exhausted")

        self._call_count += 1
        logger.info("AI fallback call %d/%d for failed step", self._call_count, self.max_calls)
        logger.debug("Fallback context: %s", test_context)
        logger.debug("Fallback original selector: %s", original_action.selector)

        user_message = build_fallback_prompt(
            test_context=test_context,
            dom_snippet=dom_snippet,
            console_errors=console_errors,
            original_action_desc=original_action.description,
            original_selector=original_action.selector or "",
        )

        try:
            # Use complete_json for proper parsing + debug logging
            # For image calls, use complete_with_image then parse via AIClient
            if screenshot_path and Path(screenshot_path).exists():
                with open(screenshot_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                response_text = self.ai_client.complete_with_image(
                    system_prompt=FALLBACK_SYSTEM_PROMPT,
                    user_message=user_message,
                    image_base64=img_b64,
                    max_tokens=1000,
                )
                # Parse through the AI client's JSON parser (with cleanup + debug logging)
                data = AIClient._parse_json_response(response_text)
            else:
                # complete_json handles parsing + debug logging automatically
                data = self.ai_client.complete_json(
                    system_prompt=FALLBACK_SYSTEM_PROMPT,
                    user_message=user_message,
                    max_tokens=1000,
                )

            decision = data.get("decision", "skip")
            reasoning = data.get("reasoning", "")
            logger.debug("Fallback AI decision: %s — %s", decision, reasoning)

            new_action = None
            if data.get("new_action"):
                new_action = Action(**data["new_action"])
                logger.debug("Fallback new action: %s selector=%s",
                             new_action.action_type, new_action.selector)

            return FallbackResponse(
                decision=decision,
                new_selector=data.get("new_selector"),
                new_action=new_action,
                reasoning=reasoning,
            )

        except ValueError as e:
            # JSON parse error — already logged in detail by AIClient._save_parse_failure
            logger.error("Fallback AI response parse failed: %s", e)
            return FallbackResponse(decision="skip", reasoning=f"AI response parse failed: {e}")

        except Exception as e:
            logger.error("Fallback AI call failed: %s", e)
            # Save the error details
            try:
                AIClient._save_parse_failure(
                    call_number=self.ai_client.call_count,
                    raw_response=f"Exception during fallback call: {type(e).__name__}: {e}",
                    error=str(e),
                )
            except Exception:
                pass
            return FallbackResponse(decision="skip", reasoning=f"AI call failed: {e}")

    def to_record(self, step_index: int, original_selector: str, response: FallbackResponse) -> FallbackRecord:
        """Convert a fallback response to a record for storage."""
        return FallbackRecord(
            step_index=step_index,
            original_selector=original_selector,
            decision=response.decision,
            new_selector=response.new_selector,
            reasoning=response.reasoning,
        )
