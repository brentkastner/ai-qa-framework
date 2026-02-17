"""Tests for the smart authentication module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.auth.smart_auth import (
    SmartAuthResult,
    _find_password_field,
    _find_username_field,
    _score_login_form,
    perform_smart_auth,
)
from src.models.config import AuthConfig
from src.models.site_model import FormField, FormModel


# ============================================================================
# Helpers
# ============================================================================


def _make_form(
    fields: list[tuple[str, str]],
    action: str = "/login",
    submit_selector: str = "button[type='submit']",
) -> FormModel:
    """Create a FormModel with given (name, field_type) pairs."""
    form_fields = [
        FormField(name=name, field_type=ftype, selector=f"input[name='{name}']")
        for name, ftype in fields
    ]
    return FormModel(
        form_id="test-form",
        action=action,
        method="POST",
        fields=form_fields,
        submit_selector=submit_selector,
    )


# ============================================================================
# Scoring tests
# ============================================================================


class TestScoreLoginForm:
    def test_typical_login_form_scores_high(self):
        form = _make_form([("email", "email"), ("password", "password")])
        score = _score_login_form(form)
        assert score >= 12, f"Typical login form should score >= 12, got {score}"

    def test_registration_form_scores_lower(self):
        form = _make_form([
            ("name", "text"),
            ("email", "email"),
            ("password", "password"),
            ("confirm_password", "password"),
            ("phone", "tel"),
            ("address", "text"),
        ])
        score = _score_login_form(form)
        # Registration forms have many fields, so should lose the "small form" bonus
        login_form = _make_form([("email", "email"), ("password", "password")])
        login_score = _score_login_form(login_form)
        assert login_score > score, "Login form should score higher than registration form"

    def test_search_form_scores_low(self):
        form = _make_form([("q", "text")], action="/search", submit_selector="")
        score = _score_login_form(form)
        assert score < 12, f"Search form should score < 12, got {score}"

    def test_login_action_keyword_bonus(self):
        form_with_keyword = _make_form(
            [("user", "text"), ("pass", "password")], action="/api/login"
        )
        form_without_keyword = _make_form(
            [("user", "text"), ("pass", "password")], action="/api/submit"
        )
        assert _score_login_form(form_with_keyword) > _score_login_form(form_without_keyword)


# ============================================================================
# Field identification tests
# ============================================================================


class TestFindPasswordField:
    def test_finds_password_field(self):
        form = _make_form([("email", "email"), ("password", "password")])
        assert _find_password_field(form) == "input[name='password']"

    def test_returns_none_when_no_password(self):
        form = _make_form([("email", "email"), ("name", "text")])
        assert _find_password_field(form) is None


class TestFindUsernameField:
    def test_prefers_email_type(self):
        form = _make_form([("login", "text"), ("email", "email"), ("password", "password")])
        assert _find_username_field(form) == "input[name='email']"

    def test_falls_back_to_name_keyword(self):
        form = _make_form([("username", "text"), ("other", "text"), ("password", "password")])
        assert _find_username_field(form) == "input[name='username']"

    def test_falls_back_to_lone_text_field(self):
        form = _make_form([("foo", "text"), ("password", "password")])
        assert _find_username_field(form) == "input[name='foo']"

    def test_returns_none_when_no_candidates(self):
        form = _make_form([("password", "password")])
        assert _find_username_field(form) is None


# ============================================================================
# Tier 1: Explicit selectors
# ============================================================================


class TestExplicitSelectors:
    @pytest.mark.asyncio
    async def test_uses_explicit_selectors_when_all_provided(self):
        config = AuthConfig(
            login_url="https://example.com/login",
            username="user",
            password="pass",
            username_selector="#user",
            password_selector="#pass",
            submit_selector="#submit",
        )
        context = AsyncMock()
        page = AsyncMock()
        page.url = "https://example.com/dashboard"  # URL changed = success
        context.new_page.return_value = page

        # Mock evaluate to say no visible password field (login succeeded)
        page.evaluate = AsyncMock(return_value=False)

        result = await perform_smart_auth(context, config)

        assert result.success
        assert result.auth_flow.detection_method == "explicit"
        page.fill.assert_any_call("#user", "user")
        page.fill.assert_any_call("#pass", "pass")
        page.click.assert_called_once_with("#submit")

    @pytest.mark.asyncio
    async def test_uses_explicit_when_auto_detect_disabled(self):
        config = AuthConfig(
            login_url="https://example.com/login",
            username="user",
            password="pass",
            username_selector="#user",
            password_selector="#pass",
            submit_selector="#submit",
            auto_detect=False,
        )
        context = AsyncMock()
        page = AsyncMock()
        page.url = "https://example.com/home"
        context.new_page.return_value = page
        page.evaluate = AsyncMock(return_value=False)

        result = await perform_smart_auth(context, config)

        assert result.success
        assert result.auth_flow.detection_method == "explicit"


# ============================================================================
# Config backwards compatibility
# ============================================================================


class TestAuthConfigBackwardsCompat:
    def test_empty_selectors_by_default(self):
        config = AuthConfig(
            login_url="https://example.com/login",
            username="user",
            password="pass",
        )
        assert config.username_selector == ""
        assert config.password_selector == ""
        assert config.submit_selector == ""
        assert config.auto_detect is True
        assert config.llm_fallback is True

    def test_explicit_selectors_preserved(self):
        config = AuthConfig(
            login_url="https://example.com/login",
            username="user",
            password="pass",
            username_selector="input[name='username']",
            password_selector="input[type='password']",
            submit_selector="button[type='submit']",
        )
        assert config.username_selector == "input[name='username']"

    def test_old_config_json_parses(self):
        """Simulate loading an old config that doesn't have new fields."""
        old_config_data = {
            "login_url": "https://example.com/login",
            "username": "user",
            "password": "pass",
        }
        config = AuthConfig(**old_config_data)
        assert config.auto_detect is True
        assert config.llm_fallback is True

    def test_env_password_still_works(self, monkeypatch):
        monkeypatch.setenv("TEST_PW", "secret123")
        config = AuthConfig(
            login_url="https://example.com/login",
            username="user",
            password="env:TEST_PW",
        )
        assert config.password == "secret123"


# ============================================================================
# Model backwards compatibility
# ============================================================================


class TestModelBackwardsCompat:
    def test_page_model_auth_required_default(self):
        from src.models.site_model import PageModel
        page = PageModel(page_id="test", url="https://example.com")
        assert page.auth_required is None

    def test_auth_flow_new_fields_default(self):
        from src.models.site_model import AuthFlow
        flow = AuthFlow(login_url="https://example.com/login")
        assert flow.detection_method == ""
        assert flow.detected_selectors == {}

    def test_old_auth_flow_json_parses(self):
        """Old serialized AuthFlow without new fields should deserialize."""
        from src.models.site_model import AuthFlow
        old_data = {
            "login_url": "https://example.com/login",
            "login_method": "form",
            "requires_credentials": True,
        }
        flow = AuthFlow(**old_data)
        assert flow.detection_method == ""
        assert flow.detected_selectors == {}
