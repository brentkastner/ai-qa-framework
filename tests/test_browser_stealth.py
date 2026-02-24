"""Tests for browser stealth utilities — video recording parameter support."""

import pytest
from unittest.mock import AsyncMock

from src.utils.browser_stealth import create_stealth_context


class TestCreateStealthContext:
    """Tests for create_stealth_context with video recording support."""

    @pytest.mark.asyncio
    async def test_no_video_by_default(self):
        """When record_video_dir is not provided, no video kwargs are passed."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await create_stealth_context(
            mock_browser, viewport={"width": 1280, "height": 720},
        )

        call_kwargs = mock_browser.new_context.call_args.kwargs
        assert "record_video_dir" not in call_kwargs
        assert "record_video_size" not in call_kwargs

    @pytest.mark.asyncio
    async def test_video_dir_passed_when_provided(self):
        """When record_video_dir is given, both dir and size are passed."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await create_stealth_context(
            mock_browser,
            viewport={"width": 1280, "height": 720},
            record_video_dir="/tmp/video",
        )

        call_kwargs = mock_browser.new_context.call_args.kwargs
        assert call_kwargs["record_video_dir"] == "/tmp/video"
        assert call_kwargs["record_video_size"] == {"width": 1280, "height": 720}

    @pytest.mark.asyncio
    async def test_no_video_when_none(self):
        """Explicit None for record_video_dir behaves like omitting it."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await create_stealth_context(
            mock_browser,
            viewport={"width": 1280, "height": 720},
            record_video_dir=None,
        )

        call_kwargs = mock_browser.new_context.call_args.kwargs
        assert "record_video_dir" not in call_kwargs
        assert "record_video_size" not in call_kwargs

    @pytest.mark.asyncio
    async def test_stealth_script_applied(self):
        """Stealth init script is always added regardless of video setting."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await create_stealth_context(
            mock_browser,
            viewport={"width": 1280, "height": 720},
            record_video_dir="/tmp/video",
        )

        mock_context.add_init_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_storage_state_preserved_with_video(self):
        """Storage state is correctly passed alongside video recording."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        fake_storage = {"cookies": [{"name": "session", "value": "abc"}]}

        await create_stealth_context(
            mock_browser,
            viewport={"width": 640, "height": 360},
            storage_state=fake_storage,
            record_video_dir="/tmp/video",
        )

        call_kwargs = mock_browser.new_context.call_args.kwargs
        assert call_kwargs["storage_state"] == fake_storage
        assert call_kwargs["record_video_dir"] == "/tmp/video"
        assert call_kwargs["record_video_size"] == {"width": 640, "height": 360}
