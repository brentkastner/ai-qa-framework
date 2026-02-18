"""Smart authentication — auto-detects login forms and authenticates."""

from __future__ import annotations

import base64
import logging
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

from src.models.config import AuthConfig
from src.models.site_model import AuthFlow

logger = logging.getLogger(__name__)

# Keywords that suggest a form action is login-related
_LOGIN_ACTION_KEYWORDS = ("login", "signin", "sign-in", "auth", "session", "log-in")

# Keywords that suggest a field name is for username/email
_USERNAME_NAME_KEYWORDS = ("user", "login", "email", "account", "uname", "identifier")


class SmartAuthResult:
    """Result of an authentication attempt."""

    def __init__(
        self,
        success: bool,
        auth_flow: Optional[AuthFlow] = None,
        error: Optional[str] = None,
        post_login_url: Optional[str] = None,
    ):
        self.success = success
        self.auth_flow = auth_flow
        self.error = error
        self.post_login_url = post_login_url


async def perform_smart_auth(
    context: BrowserContext,
    auth_config: AuthConfig,
    ai_client=None,
) -> SmartAuthResult:
    """Authenticate using a three-tier detection strategy.

    Tier 1: Use explicit selectors if all are provided.
    Tier 2: Auto-detect login form via heuristics on form_analyzer output.
    Tier 3: LLM vision fallback — screenshot + DOM sent to Claude.
    """
    logger.info("Smart auth: navigating to %s", auth_config.login_url)
    page = await context.new_page()
    try:
        await page.goto(auth_config.login_url, wait_until="networkidle", timeout=30000)

        logger.debug("Smart auth: resolving login form selectors...")
        selectors = await _resolve_selectors(page, auth_config, ai_client)
        if selectors is None:
            logger.debug("Smart auth: no login form selectors found")
            return SmartAuthResult(
                success=False,
                error="Could not identify login form fields",
            )

        username_sel, password_sel, submit_sel, method = selectors
        logger.debug("Smart auth: selectors resolved — username=%s, password=%s, submit=%s",
                      username_sel, password_sel, submit_sel)

        # Fill and submit
        logger.info("Smart auth: filling form (method=%s)", method)
        await page.fill(username_sel, auth_config.username)
        await page.fill(password_sel, auth_config.password)
        await page.click(submit_sel)

        # Verify success
        success = await _verify_login_success(page, auth_config)
        if success:
            # After login verification, wait for any JS-triggered redirect.
            # Login pages often redirect via JS (e.g., window.location = '/dashboard')
            # after the fetch response is processed — this may happen AFTER networkidle.
            login_url_normalized = auth_config.login_url.rstrip("/")
            try:
                await page.wait_for_url(
                    lambda url: url.rstrip("/") != login_url_normalized,
                    timeout=5000,
                )
                # URL changed — wait for the new page to settle
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
            except Exception:
                pass  # URL may not change (SPA, in-place auth)

            post_login_url = page.url
            logger.info("Smart auth: login successful (method=%s), landed on %s",
                        method, post_login_url)
            return SmartAuthResult(
                success=True,
                post_login_url=post_login_url,
                auth_flow=AuthFlow(
                    login_url=auth_config.login_url,
                    login_method="form",
                    requires_credentials=True,
                    detection_method=method,
                    detected_selectors={
                        "username": username_sel,
                        "password": password_sel,
                        "submit": submit_sel,
                    },
                ),
            )
        else:
            return SmartAuthResult(
                success=False,
                error=f"Login form submitted (method={method}) but verification failed — "
                      f"page may still show login form or URL did not change",
            )

    except Exception as e:
        logger.error("Smart auth failed: %s", e)
        return SmartAuthResult(success=False, error=str(e))
    finally:
        await page.close()


async def _resolve_selectors(
    page: Page,
    auth_config: AuthConfig,
    ai_client,
) -> Optional[tuple[str, str, str, str]]:
    """Resolve username, password, and submit selectors.

    Returns (username_sel, password_sel, submit_sel, detection_method) or None.
    """
    # Tier 1: Explicit selectors
    logger.debug("Smart auth: checking Tier 1 — explicit selectors")
    if (
        not auth_config.auto_detect
        or (auth_config.username_selector and auth_config.password_selector and auth_config.submit_selector)
    ):
        logger.info("Smart auth: using explicit selectors")
        return (
            auth_config.username_selector,
            auth_config.password_selector,
            auth_config.submit_selector,
            "explicit",
        )

    # Tier 2: Auto-detect via form analysis + heuristics
    if auth_config.auto_detect:
        logger.debug("Smart auth: trying Tier 2 — auto-detect via form analysis")
        result = await _auto_detect_login_form(page)
        if result is not None:
            logger.info("Smart auth: auto-detected login form")
            return (*result, "auto_detect")
        logger.debug("Smart auth: Tier 2 auto-detect did not find login form")

    # Tier 3: LLM vision fallback
    if auth_config.llm_fallback and ai_client is not None:
        logger.debug("Smart auth: trying Tier 3 — LLM vision fallback")
        result = await _llm_detect_login_form(page, auth_config, ai_client)
        if result is not None:
            logger.info("Smart auth: LLM identified login form")
            return (*result, "llm_fallback")
        logger.debug("Smart auth: Tier 3 LLM fallback did not identify form")

    # All tiers failed — try explicit selectors as last resort if any were provided
    if auth_config.username_selector or auth_config.password_selector:
        u = auth_config.username_selector or "input[type='text'], input[type='email']"
        p = auth_config.password_selector or "input[type='password']"
        s = auth_config.submit_selector or "button[type='submit'], button"
        logger.warning("Smart auth: falling back to partial/default selectors")
        return (u, p, s, "explicit")

    return None


# ---------------------------------------------------------------------------
# Tier 2: Auto-detection via form_analyzer + heuristics
# ---------------------------------------------------------------------------


async def _auto_detect_login_form(
    page: Page,
) -> Optional[tuple[str, str, str]]:
    """Analyze forms on the page and identify the login form via heuristics."""
    from src.crawler.form_analyzer import analyze_forms

    forms = await analyze_forms(page)

    # Score each form
    best_form = None
    best_score = 0

    for form in forms:
        score = _score_login_form(form)
        if score > best_score:
            best_score = score
            best_form = form

    # Also check for orphan password fields (no <form> wrapper)
    if best_score < 12:
        orphan_result = await _detect_orphan_login_fields(page)
        if orphan_result is not None:
            return orphan_result

    if best_form is None or best_score < 12:
        logger.debug("Auto-detect: no form scored high enough (best=%d)", best_score)
        return None

    # Identify fields within the winning form
    password_sel = _find_password_field(best_form)
    if not password_sel:
        logger.debug("Auto-detect: no password field found in best form")
        return None

    username_sel = _find_username_field(best_form)
    if not username_sel:
        logger.debug("Auto-detect: no username field found in best form")
        return None

    submit_sel = best_form.submit_selector
    if not submit_sel:
        submit_sel = "button[type='submit'], button"

    return (username_sel, password_sel, submit_sel)


def _score_login_form(form) -> int:
    """Score a form on how likely it is to be a login form."""
    score = 0

    has_password = any(f.field_type == "password" for f in form.fields)
    has_text_or_email = any(f.field_type in ("text", "email") for f in form.fields)
    field_count = len(form.fields)

    if has_password:
        score += 10
    if has_text_or_email:
        score += 5
    if 1 <= field_count <= 4:
        score += 3
    if field_count < 6:
        score += 1
    if form.submit_selector:
        score += 2

    action_lower = (form.action or "").lower()
    if any(kw in action_lower for kw in _LOGIN_ACTION_KEYWORDS):
        score += 3

    return score


def _find_password_field(form) -> Optional[str]:
    """Find the password field selector in a form."""
    for field in form.fields:
        if field.field_type == "password" and field.selector:
            return field.selector
    return None


def _find_username_field(form) -> Optional[str]:
    """Find the username/email field selector using heuristics."""
    # Priority 1: email type field
    for field in form.fields:
        if field.field_type == "email" and field.selector:
            return field.selector

    # Priority 2: field name contains username-related keywords
    for field in form.fields:
        if field.field_type in ("text", "email", "tel") and field.selector:
            name_lower = (field.name or "").lower()
            if any(kw in name_lower for kw in _USERNAME_NAME_KEYWORDS):
                return field.selector

    # Priority 3: lone text field (not password)
    text_fields = [
        f for f in form.fields
        if f.field_type in ("text", "email", "tel") and f.selector
    ]
    if len(text_fields) == 1:
        return text_fields[0].selector

    # Priority 4: first text field
    if text_fields:
        return text_fields[0].selector

    return None


async def _detect_orphan_login_fields(page: Page) -> Optional[tuple[str, str, str]]:
    """Detect login fields that aren't wrapped in a <form> tag (common in SPAs)."""
    try:
        result = await page.evaluate("""() => {
            // Find all password inputs
            const passwordInputs = Array.from(document.querySelectorAll('input[type="password"]'));
            if (passwordInputs.length === 0) return null;

            // Take the first visible password input
            const pwInput = passwordInputs.find(el => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            });
            if (!pwInput) return null;

            // Check if it's inside a <form> — if so, form_analyzer already handled it
            if (pwInput.closest('form')) return null;

            // Build password selector
            let pwSelector = '';
            if (pwInput.id) pwSelector = '#' + CSS.escape(pwInput.id);
            else if (pwInput.name) pwSelector = 'input[name="' + pwInput.name + '"]';
            else pwSelector = 'input[type="password"]';

            // Find the username field: look for text/email inputs near the password field
            const container = pwInput.closest('div, section, main, [role="dialog"], [class*="login"], [class*="auth"]') || document.body;
            const textInputs = Array.from(container.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"]'))
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });

            if (textInputs.length === 0) return null;

            const userInput = textInputs[0];
            let userSelector = '';
            if (userInput.id) userSelector = '#' + CSS.escape(userInput.id);
            else if (userInput.name) userSelector = 'input[name="' + userInput.name + '"]';
            else userSelector = 'input[type="' + (userInput.type || 'text') + '"]';

            // Find submit button near the password field
            const buttons = Array.from(container.querySelectorAll('button, input[type="submit"], [role="button"]'))
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });

            let submitSelector = '';
            // Prefer button[type="submit"]
            const submitBtn = buttons.find(b => b.type === 'submit');
            if (submitBtn) {
                if (submitBtn.id) submitSelector = '#' + CSS.escape(submitBtn.id);
                else submitSelector = 'button[type="submit"]';
            } else if (buttons.length > 0) {
                const btn = buttons[0];
                if (btn.id) submitSelector = '#' + CSS.escape(btn.id);
                else submitSelector = 'button';
            }

            if (!submitSelector) return null;

            return { username: userSelector, password: pwSelector, submit: submitSelector };
        }""")

        if result is None:
            return None

        return (result["username"], result["password"], result["submit"])

    except Exception as e:
        logger.debug("Orphan login field detection failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Tier 3: LLM vision fallback
# ---------------------------------------------------------------------------


async def _llm_detect_login_form(
    page: Page,
    auth_config: AuthConfig,
    ai_client,
) -> Optional[tuple[str, str, str]]:
    """Use LLM vision to identify login form selectors."""
    from src.ai.client import AIClient
    from src.ai.prompts.auth import AUTH_DETECTION_SYSTEM_PROMPT, build_auth_detection_prompt

    try:
        screenshot_bytes = await page.screenshot()
        img_b64 = base64.b64encode(screenshot_bytes).decode()
        dom_content = await page.content()

        user_message = build_auth_detection_prompt(dom_content, auth_config.login_url)
        response_text = ai_client.complete_with_image(
            system_prompt=AUTH_DETECTION_SYSTEM_PROMPT,
            user_message=user_message,
            image_base64=img_b64,
            max_tokens=1000,
        )

        data = AIClient._parse_json_response(response_text)
        confidence = data.get("confidence", 0)
        reasoning = data.get("reasoning", "")
        logger.info("LLM auth detection: confidence=%.2f, reasoning=%s", confidence, reasoning)

        if confidence < 0.5:
            logger.warning("LLM auth detection confidence too low: %.2f", confidence)
            return None

        username_sel = data.get("username_selector", "")
        password_sel = data.get("password_selector", "")
        submit_sel = data.get("submit_selector", "")

        if not username_sel or not password_sel or not submit_sel:
            logger.warning("LLM returned incomplete selectors")
            return None

        return (username_sel, password_sel, submit_sel)

    except Exception as e:
        logger.error("LLM auth detection failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Login verification
# ---------------------------------------------------------------------------


async def authenticate_and_capture_state(
    browser: Browser,
    auth_config: AuthConfig,
    ai_client=None,
    viewport: dict | None = None,
    user_agent: str | None = None,
) -> tuple[SmartAuthResult, dict | None]:
    """Authenticate in a temporary context and capture the resulting storage state.

    Creates a disposable browser context, performs the full smart auth flow,
    and on success captures cookies + localStorage via Playwright's storageState().
    The temporary context is always closed before returning.

    Returns:
        A tuple of (SmartAuthResult, storage_state_dict_or_None).
        storage_state is None if authentication failed.
    """
    from src.utils.browser_stealth import create_stealth_context

    context = await create_stealth_context(
        browser,
        viewport=viewport or {"width": 1280, "height": 720},
        user_agent=user_agent,
    )
    try:
        result = await perform_smart_auth(context, auth_config, ai_client=ai_client)
        storage_state = None
        if result.success:
            storage_state = await context.storage_state()
            logger.info("Captured auth storage state (%d cookies)",
                        len(storage_state.get("cookies", [])))
        return result, storage_state
    finally:
        await context.close()


async def _verify_login_success(page: Page, auth_config: AuthConfig) -> bool:
    """Verify that login was successful after form submission."""
    logger.debug("Smart auth: verifying login success...")
    # Wait for navigation / network activity
    if auth_config.success_indicator:
        logger.debug("Smart auth: checking success indicator: %s", auth_config.success_indicator)
        try:
            await page.wait_for_selector(auth_config.success_indicator, timeout=10000)
            return True
        except Exception:
            # Fall through to other checks
            pass

    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    # Check 1: URL changed away from login page
    current_url = page.url
    logger.debug("Smart auth: checking URL change — current=%s, login=%s",
                  current_url, auth_config.login_url)
    if current_url != auth_config.login_url:
        login_path = auth_config.login_url.rstrip("/")
        current_path = current_url.rstrip("/")
        if current_path != login_path:
            return True

    # Check 2: Login form is no longer present (password field gone)
    try:
        has_password = await page.evaluate("""() => {
            const pw = document.querySelector('input[type="password"]');
            if (!pw) return false;
            const rect = pw.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }""")
        if not has_password:
            return True
    except Exception:
        pass

    # If success_indicator was set and we got here, login likely failed
    if auth_config.success_indicator:
        return False

    # If we get here with no success_indicator, assume success
    # (the page loaded without error after submit)
    return True
