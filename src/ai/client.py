"""Claude API client wrapper for the QA framework."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import traceback
from pathlib import Path
from typing import Any, Optional

import anthropic

logger = logging.getLogger(__name__)

# Configurable debug directory — set by orchestrator at startup
_debug_dir: Path | None = None


def set_debug_dir(path: Path) -> None:
    """Set the directory for dumping failed AI responses."""
    global _debug_dir
    _debug_dir = path
    _debug_dir.mkdir(parents=True, exist_ok=True)


def _get_debug_dir() -> Path:
    """Get or create the debug directory."""
    global _debug_dir
    if _debug_dir is None:
        _debug_dir = Path("./qa-framework") / "debug"
    _debug_dir.mkdir(parents=True, exist_ok=True)
    return _debug_dir


class AIClient:
    """Wrapper around the Anthropic Claude API."""

    def __init__(self, model: str = "claude-opus-4-6", max_tokens: int = 32000):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Please set it before running the framework."
            )
        # Set a longer timeout for large planning requests (30 minutes)
        self.client = anthropic.Anthropic(api_key=api_key, timeout=1800.0)
        self.model = model
        self.max_tokens = max_tokens
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
    ) -> str:
        """Send a completion request to Claude and return the text response."""
        self._call_count += 1
        tokens = max_tokens or self.max_tokens
        logger.info(
            "Calling AI (call #%d, model=%s, max_tokens=%d)...",
            self._call_count, self.model, tokens,
        )
        logger.debug("AI prompt length: system=%d chars, user=%d chars",
                      len(system_prompt), len(user_message))

        try:
            call_start = time.time()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            call_duration = time.time() - call_start
            text = response.content[0].text
            logger.info("AI response received in %.1fs (%d chars)",
                        call_duration, len(text))

            # Detect if response was truncated due to token limit
            if response.stop_reason == "max_tokens":
                logger.warning(
                    "AI response was truncated! Hit max_tokens limit (%d). "
                    "Response may be incomplete. Consider increasing ai_max_planning_tokens in config.",
                    tokens
                )

            # Always log full exchange for debugging
            self._save_exchange_log(
                call_number=self._call_count,
                system_prompt=system_prompt,
                user_message=user_message,
                response_text=text,
                error=None,
            )

            return text
        except anthropic.APIError as e:
            logger.error("Claude API error: %s", e)
            self._save_exchange_log(
                call_number=self._call_count,
                system_prompt=system_prompt,
                user_message=user_message,
                response_text="",
                error=str(e),
            )
            raise

    def complete_json(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Send a completion request and parse the response as JSON."""
        text = self.complete(system_prompt, user_message, max_tokens, temperature)
        return self._parse_json_response(text)

    def complete_with_image(
        self,
        system_prompt: str,
        user_message: str,
        image_base64: str,
        media_type: str = "image/png",
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send a completion request with an image (for fallback analysis)."""
        self._call_count += 1
        tokens = max_tokens or self.max_tokens
        logger.info(
            "Calling AI with image (call #%d, model=%s, max_tokens=%d)...",
            self._call_count, self.model, tokens,
        )

        try:
            call_start = time.time()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": user_message},
                        ],
                    }
                ],
            )
            call_duration = time.time() - call_start
            text = response.content[0].text
            logger.info("AI image response received in %.1fs (%d chars)",
                        call_duration, len(text))
            self._save_exchange_log(
                call_number=self._call_count,
                system_prompt=system_prompt,
                user_message=f"[IMAGE ATTACHED]\n{user_message}",
                response_text=text,
                error=None,
            )
            return text
        except anthropic.APIError as e:
            logger.error("Claude API error (with image): %s", e)
            self._save_exchange_log(
                call_number=self._call_count,
                system_prompt=system_prompt,
                user_message=f"[IMAGE ATTACHED]\n{user_message}",
                response_text="",
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # JSON parsing with LLM quirk handling
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Parse AI response as JSON, handling common LLM output quirks."""
        original_text = text
        text = text.strip()

        # Strip markdown code fences using regex for robustness
        # Handles: ```json, ```, with/without language identifier, extra whitespace
        fence_pattern = re.compile(
            r'^```(?:json|python|javascript|)?\s*\n(.*?)\n```\s*$',
            re.DOTALL | re.MULTILINE
        )
        match = fence_pattern.search(text)
        if match:
            text = match.group(1).strip()
            logger.debug("Stripped markdown code fences from AI response")
        else:
            logger.debug("No markdown code fences detected in AI response")

        text = text.strip()

        # Validate that markdown was properly stripped
        if text.startswith('```') or text.endswith('```'):
            logger.warning("Markdown fences still present after stripping attempt")
            # Try one more aggressive strip
            text = text.lstrip('`').rstrip('`').strip()

        # Validate JSON boundaries exist
        if not text.startswith('{'):
            logger.error("Response doesn't start with '{' after cleaning: %s", text[:100])
        if not text.endswith('}'):
            logger.error("Response doesn't end with '}' after cleaning: %s", text[-100:])

        # Attempt 1: Parse with strict=False (handles control chars)
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            pass

        # Attempt 2: Clean up common issues
        cleaned = text

        # Remove // comments (not inside strings — heuristic: after }, ], or line start)
        cleaned = re.sub(r'(?<=[\s,\]\}])//[^\n]*', '', cleaned)
        cleaned = re.sub(r'^//[^\n]*', '', cleaned, flags=re.MULTILINE)

        # Remove trailing commas
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

        # Escape control characters
        def _escape_control_chars(s: str) -> str:
            result = []
            for ch in s:
                cp = ord(ch)
                if cp < 0x20 and ch not in ('\n', '\r'):
                    result.append(f'\\u{cp:04x}')
                else:
                    result.append(ch)
            return ''.join(result)

        cleaned = _escape_control_chars(cleaned)

        # Extract JSON object boundaries
        first_brace = cleaned.find('{')
        last_brace = cleaned.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]

        # Attempt 3: Parse cleaned text
        try:
            return json.loads(cleaned, strict=False)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse AI response as JSON: %s", e)
            # Always log the full failure details (both original and cleaned text)
            AIClient._save_parse_failure(
                call_number=0,  # unknown when called statically
                raw_response=original_text,
                error=str(e),
                cleaned_response=cleaned,
            )
            raise ValueError(f"AI returned invalid JSON: {e}") from e

    # ------------------------------------------------------------------
    # Debug logging
    # ------------------------------------------------------------------

    @staticmethod
    def _save_exchange_log(
        call_number: int,
        system_prompt: str,
        user_message: str,
        response_text: str,
        error: str | None,
    ) -> None:
        """Save the full AI exchange (prompt + response) to a log file."""
        try:
            debug_dir = _get_debug_dir()
            ts = time.strftime("%Y%m%d_%H%M%S")
            log_file = debug_dir / f"ai_call_{ts}_{call_number:03d}.log"

            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"=== AI CALL #{call_number} at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
                f.write(f"=== SYSTEM PROMPT ({len(system_prompt)} chars) ===\n")
                f.write(system_prompt)
                f.write(f"\n\n=== USER MESSAGE ({len(user_message)} chars) ===\n")
                f.write(user_message)
                f.write(f"\n\n=== RESPONSE ({len(response_text)} chars) ===\n")
                f.write(response_text if response_text else "(empty)")
                if error:
                    f.write(f"\n\n=== ERROR ===\n{error}\n")

            logger.debug("AI exchange logged to %s", log_file)
        except Exception as log_err:
            logger.debug("Failed to save AI exchange log: %s", log_err)

    @staticmethod
    def _save_parse_failure(
        call_number: int,
        raw_response: str,
        error: str,
        cleaned_response: str = None,
    ) -> None:
        """Save detailed parse failure info for debugging."""
        try:
            debug_dir = _get_debug_dir()
            ts = time.strftime("%Y%m%d_%H%M%S")
            fail_file = debug_dir / f"parse_failure_{ts}_{call_number:03d}.log"

            # Find the problematic area - use cleaned_response if available, otherwise raw_response
            text_to_parse = cleaned_response if cleaned_response is not None else raw_response
            detail = ""
            try:
                json.loads(text_to_parse, strict=False)
            except json.JSONDecodeError as e:
                line_no = e.lineno
                col_no = e.colno
                lines = text_to_parse.split('\n')
                start = max(0, line_no - 3)
                end = min(len(lines), line_no + 3)
                context_lines = []
                for i in range(start, end):
                    marker = " >>> " if i == line_no - 1 else "     "
                    context_lines.append(f"{marker}{i+1:4d} | {lines[i]}")
                    if i == line_no - 1:
                        context_lines.append(f"     {'':>4s}   {' ' * max(0, col_no - 1)}^--- error here")
                detail = "\n".join(context_lines)

            with open(fail_file, "w", encoding="utf-8") as f:
                f.write(f"=== JSON PARSE FAILURE (call #{call_number}) ===\n\n")
                f.write(f"Error: {error}\n\n")
                if detail:
                    context_source = "CLEANED TEXT" if cleaned_response is not None else "RAW RESPONSE"
                    f.write(f"=== ERROR CONTEXT (from {context_source}) ===\n{detail}\n\n")
                if cleaned_response is not None:
                    f.write(f"=== CLEANED TEXT ({len(cleaned_response)} chars) ===\n")
                    f.write(cleaned_response)
                    f.write(f"\n\n=== FULL RAW RESPONSE ({len(raw_response)} chars) ===\n")
                    f.write(raw_response)
                else:
                    f.write(f"=== FULL RAW RESPONSE ({len(raw_response)} chars) ===\n")
                    f.write(raw_response)
                # Also show hex dump of chars around the error position
                try:
                    err_match = re.search(r'char (\d+)', error)
                    if err_match:
                        pos = int(err_match.group(1))
                        start = max(0, pos - 20)
                        end = min(len(raw_response), pos + 20)
                        snippet = raw_response[start:end]
                        hex_dump = " ".join(f"{ord(c):02x}" for c in snippet)
                        char_dump = "".join(c if 32 <= ord(c) < 127 else '.' for c in snippet)
                        f.write(f"\n\n=== HEX DUMP around char {pos} ===\n")
                        f.write(f"Chars {start}-{end}: {char_dump}\n")
                        f.write(f"Hex:   {hex_dump}\n")
                except Exception:
                    pass

            logger.error(
                "JSON parse failure details saved to %s (see file for full response and hex dump)",
                fail_file,
            )
        except Exception as log_err:
            logger.error("Failed to save parse failure log: %s", log_err)
            logger.error("Raw response (first 2000 chars):\n%s", raw_response[:2000])
