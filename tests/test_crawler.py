"""Tests for the crawler module — crawler, element_extractor, form_analyzer, spa_handler."""

import asyncio
import heapq
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.crawler.crawler import (
    PRIORITY_ORGANIC,
    PRIORITY_SITEMAP,
    PRIORITY_START,
    Crawler,
    _CrawlEntry,
    _is_same_origin,
    _is_valid_page_url,
    _matches_patterns,
    _normalize_url,
    _page_id,
)
from src.crawler.element_extractor import extract_elements
from src.crawler.form_analyzer import analyze_forms
from src.crawler.spa_handler import detect_spa_type, discover_spa_routes
from src.models.config import CrawlConfig, FrameworkConfig, ViewportConfig
from src.models.site_model import ElementModel, FormField, FormModel


# ============================================================================
# Helper function tests
# ============================================================================


class TestNormalizeUrl:
    """Tests for _normalize_url (thin wrapper around url_utils)."""

    def test_strips_trailing_slash(self):
        assert _normalize_url("https://example.com/page/") == "https://example.com/page"

    def test_preserves_bare_domain(self):
        assert _normalize_url("https://example.com") == "https://example.com/"

    def test_sorts_query_params(self):
        result = _normalize_url("https://example.com/page?z=1&a=2")
        assert result == "https://example.com/page?a=2&z=1"


class TestPageId:
    """Tests for _page_id (thin wrapper around url_utils)."""

    def test_returns_12_char_hex(self):
        pid = _page_id("https://example.com/login")
        assert len(pid) == 12
        assert all(c in "0123456789abcdef" for c in pid)

    def test_same_url_same_id(self):
        assert _page_id("https://example.com/a") == _page_id("https://example.com/a")

    def test_different_url_different_id(self):
        assert _page_id("https://example.com/a") != _page_id("https://example.com/b")


class TestIsSameOrigin:
    """Tests for _is_same_origin."""

    def test_same_origin(self):
        assert _is_same_origin("https://example.com", "https://example.com/page")

    def test_different_origin(self):
        assert not _is_same_origin("https://example.com", "https://other.com/page")

    def test_different_subdomain(self):
        assert not _is_same_origin("https://www.example.com", "https://api.example.com")

    def test_different_port(self):
        assert not _is_same_origin("https://example.com:443", "https://example.com:8080")

    def test_same_origin_with_paths(self):
        assert _is_same_origin("https://example.com/a", "https://example.com/b/c/d")


class TestIsValidPageUrl:
    """Tests for _is_valid_page_url."""

    def test_valid_http(self):
        assert _is_valid_page_url("http://example.com/page")

    def test_valid_https(self):
        assert _is_valid_page_url("https://example.com/page")

    def test_rejects_ftp(self):
        assert not _is_valid_page_url("ftp://example.com/file")

    def test_rejects_javascript(self):
        assert not _is_valid_page_url("javascript:void(0)")

    def test_rejects_image_extensions(self):
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"):
            assert not _is_valid_page_url(f"https://example.com/image{ext}")

    def test_rejects_static_asset_extensions(self):
        for ext in (".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot"):
            assert not _is_valid_page_url(f"https://example.com/file{ext}")

    def test_rejects_binary_extensions(self):
        for ext in (".pdf", ".zip", ".tar", ".gz", ".mp3", ".mp4", ".webm"):
            assert not _is_valid_page_url(f"https://example.com/file{ext}")

    def test_rejects_data_extensions(self):
        for ext in (".xml", ".rss", ".atom", ".json"):
            assert not _is_valid_page_url(f"https://example.com/file{ext}")

    def test_accepts_html_page(self):
        assert _is_valid_page_url("https://example.com/page.html")

    def test_accepts_no_extension(self):
        assert _is_valid_page_url("https://example.com/dashboard")

    def test_case_insensitive(self):
        assert not _is_valid_page_url("https://example.com/image.PNG")


class TestMatchesPatterns:
    """Tests for _matches_patterns."""

    def test_matches_regex_pattern(self):
        assert _matches_patterns("https://example.com/admin/users", [r"/admin/"])

    def test_no_match(self):
        assert not _matches_patterns("https://example.com/page", [r"/admin/"])

    def test_matches_any_pattern(self):
        assert _matches_patterns("https://example.com/blog", [r"/admin/", r"/blog"])

    def test_empty_patterns(self):
        assert not _matches_patterns("https://example.com/page", [])

    def test_regex_special_chars(self):
        assert _matches_patterns("https://example.com/page?id=123", [r"\?id=\d+"])


# ============================================================================
# _CrawlEntry tests
# ============================================================================


class TestCrawlEntry:
    """Tests for _CrawlEntry priority ordering."""

    def test_lower_priority_comes_first(self):
        a = _CrawlEntry("https://example.com/a", depth=0, priority=PRIORITY_START)
        b = _CrawlEntry("https://example.com/b", depth=1, priority=PRIORITY_ORGANIC)
        assert a < b

    def test_same_priority_fifo_order(self):
        a = _CrawlEntry("https://example.com/a", depth=0, priority=PRIORITY_ORGANIC)
        b = _CrawlEntry("https://example.com/b", depth=0, priority=PRIORITY_ORGANIC)
        assert a < b  # a was created first

    def test_heap_ordering(self):
        heap = []
        sitemap = _CrawlEntry("https://example.com/sitemap-page", depth=1, priority=PRIORITY_SITEMAP)
        organic = _CrawlEntry("https://example.com/organic-page", depth=1, priority=PRIORITY_ORGANIC)
        start = _CrawlEntry("https://example.com/", depth=0, priority=PRIORITY_START)

        heapq.heappush(heap, sitemap)
        heapq.heappush(heap, organic)
        heapq.heappush(heap, start)

        assert heapq.heappop(heap).url == "https://example.com/"
        assert heapq.heappop(heap).url == "https://example.com/organic-page"
        assert heapq.heappop(heap).url == "https://example.com/sitemap-page"

    def test_stores_url_and_depth(self):
        e = _CrawlEntry("https://example.com/page", depth=3, priority=PRIORITY_ORGANIC)
        assert e.url == "https://example.com/page"
        assert e.depth == 3
        assert e.priority == PRIORITY_ORGANIC


# ============================================================================
# Crawler class tests
# ============================================================================


def _make_config(tmp_path, **overrides):
    """Create a FrameworkConfig for testing."""
    crawl_overrides = {}
    for key in list(overrides):
        if key in ("target_url", "max_pages", "max_depth", "include_patterns",
                    "exclude_patterns", "wait_for_idle"):
            crawl_overrides[key] = overrides.pop(key)

    crawl = CrawlConfig(
        target_url=crawl_overrides.get("target_url", "https://example.com"),
        max_pages=crawl_overrides.get("max_pages", 10),
        max_depth=crawl_overrides.get("max_depth", 3),
        include_patterns=crawl_overrides.get("include_patterns", []),
        exclude_patterns=crawl_overrides.get("exclude_patterns", []),
        wait_for_idle=crawl_overrides.get("wait_for_idle", False),
    )
    return FrameworkConfig(
        target_url=crawl.target_url,
        crawl=crawl,
        **overrides,
    )


class TestCrawlerInit:
    """Tests for Crawler.__init__."""

    def test_creates_baselines_dir(self, tmp_path):
        config = _make_config(tmp_path)
        output_dir = tmp_path / "output"
        crawler = Crawler(config, output_dir)
        assert (output_dir / "baselines").exists()

    def test_initializes_empty_state(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        assert crawler._visited_urls == set()
        assert crawler._queued_urls == set()
        assert crawler._pages == []
        assert crawler._nav_graph == {}
        assert crawler._api_endpoints == {}
        assert crawler._is_spa is False

    def test_stores_config(self, tmp_path):
        config = _make_config(tmp_path, max_pages=25)
        crawler = Crawler(config, tmp_path / "out")
        assert crawler.crawl_config.max_pages == 25

    def test_stores_ai_client(self, tmp_path):
        config = _make_config(tmp_path)
        mock_ai = Mock()
        crawler = Crawler(config, tmp_path / "out", ai_client=mock_ai)
        assert crawler._ai_client is mock_ai


class TestUrlInScope:
    """Tests for Crawler._url_in_scope."""

    def test_same_origin_in_scope(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        assert crawler._url_in_scope("https://example.com/page")

    def test_different_origin_out_of_scope(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        assert not crawler._url_in_scope("https://other.com/page")

    def test_exclude_patterns(self, tmp_path):
        config = _make_config(tmp_path, exclude_patterns=[r"/admin/"])
        crawler = Crawler(config, tmp_path / "out")
        assert not crawler._url_in_scope("https://example.com/admin/users")
        assert crawler._url_in_scope("https://example.com/products")

    def test_include_patterns(self, tmp_path):
        config = _make_config(tmp_path, include_patterns=[r"/products/"])
        crawler = Crawler(config, tmp_path / "out")
        assert crawler._url_in_scope("https://example.com/products/item")
        assert not crawler._url_in_scope("https://example.com/blog/post")

    def test_include_and_exclude_combined(self, tmp_path):
        config = _make_config(
            tmp_path,
            include_patterns=[r"/app/"],
            exclude_patterns=[r"/app/admin"],
        )
        crawler = Crawler(config, tmp_path / "out")
        assert crawler._url_in_scope("https://example.com/app/dashboard")
        assert not crawler._url_in_scope("https://example.com/app/admin")


class TestEnqueue:
    """Tests for Crawler._enqueue."""

    def test_enqueues_new_url(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        heap = []

        result = crawler._enqueue(heap, "https://example.com/page", depth=1, priority=PRIORITY_ORGANIC)

        assert result is True
        assert len(heap) == 1
        assert _normalize_url("https://example.com/page") in crawler._queued_urls

    def test_skips_already_queued_url(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        heap = []

        crawler._enqueue(heap, "https://example.com/page", depth=1, priority=PRIORITY_ORGANIC)
        result = crawler._enqueue(heap, "https://example.com/page", depth=1, priority=PRIORITY_ORGANIC)

        assert result is False
        assert len(heap) == 1

    def test_skips_already_visited_url(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        crawler._visited_urls.add(_normalize_url("https://example.com/page"))
        heap = []

        result = crawler._enqueue(heap, "https://example.com/page", depth=1, priority=PRIORITY_ORGANIC)

        assert result is False
        assert len(heap) == 0

    def test_skips_out_of_scope_url(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        heap = []

        result = crawler._enqueue(heap, "https://other.com/page", depth=1, priority=PRIORITY_ORGANIC)

        assert result is False

    def test_deduplicates_normalized_urls(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        heap = []

        crawler._enqueue(heap, "https://example.com/page/", depth=1, priority=PRIORITY_ORGANIC)
        result = crawler._enqueue(heap, "https://example.com/page", depth=1, priority=PRIORITY_ORGANIC)

        assert result is False
        assert len(heap) == 1


class TestResolveUrls:
    """Tests for Crawler._resolve_urls."""

    def test_resolves_relative_urls(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        result = crawler._resolve_urls(["/about", "/contact"], "https://example.com")

        assert "https://example.com/about" in result
        assert "https://example.com/contact" in result

    def test_keeps_absolute_urls(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        result = crawler._resolve_urls(
            ["https://example.com/page"], "https://example.com"
        )

        assert "https://example.com/page" in result

    def test_filters_invalid_page_urls(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        result = crawler._resolve_urls(
            ["/page", "/image.png", "/style.css"], "https://example.com"
        )

        assert "https://example.com/page" in result
        assert len([u for u in result if ".png" in u]) == 0
        assert len([u for u in result if ".css" in u]) == 0

    def test_strips_fragments(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        result = crawler._resolve_urls(
            ["/page#section"], "https://example.com"
        )

        # Fragment should be stripped (no fragment in result)
        for url in result:
            assert "#" not in url

    def test_preserves_query_params(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        result = crawler._resolve_urls(
            ["/page?id=123"], "https://example.com"
        )

        assert any("id=123" in url for url in result)

    def test_handles_empty_list(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        result = crawler._resolve_urls([], "https://example.com")
        assert result == set()

    def test_deduplicates(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        result = crawler._resolve_urls(
            ["/page", "/page", "/page"], "https://example.com"
        )

        assert len(result) == 1


class TestNavigateWithRetry:
    """Tests for Crawler._navigate_with_retry."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, tmp_path):
        config = _make_config(tmp_path, wait_for_idle=False)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_page.goto = AsyncMock(return_value=mock_resp)

        result = await crawler._navigate_with_retry(mock_page, "https://example.com")

        assert result is True
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, tmp_path):
        config = _make_config(tmp_path, wait_for_idle=False)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_page.goto = AsyncMock(
            side_effect=[RuntimeError("Timeout"), mock_resp]
        )

        with patch("src.crawler.crawler.asyncio.sleep", new_callable=AsyncMock):
            result = await crawler._navigate_with_retry(mock_page, "https://example.com")

        assert result is True
        assert mock_page.goto.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_false_after_all_retries_fail(self, tmp_path):
        config = _make_config(tmp_path, wait_for_idle=False)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=RuntimeError("Timeout"))

        with patch("src.crawler.crawler.asyncio.sleep", new_callable=AsyncMock):
            result = await crawler._navigate_with_retry(mock_page, "https://example.com", retries=1)

        assert result is False
        assert mock_page.goto.call_count == 2  # 1 initial + 1 retry

    @pytest.mark.asyncio
    async def test_waits_for_network_idle_when_configured(self, tmp_path):
        config = _make_config(tmp_path, wait_for_idle=True)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_page.goto = AsyncMock(return_value=mock_resp)
        mock_page.wait_for_load_state = AsyncMock()

        result = await crawler._navigate_with_retry(mock_page, "https://example.com")

        assert result is True
        mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=10000)

    @pytest.mark.asyncio
    async def test_network_idle_timeout_falls_back(self, tmp_path):
        config = _make_config(tmp_path, wait_for_idle=True)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_page.goto = AsyncMock(return_value=mock_resp)
        mock_page.wait_for_load_state = AsyncMock(side_effect=TimeoutError("idle timeout"))
        mock_page.wait_for_timeout = AsyncMock()

        result = await crawler._navigate_with_retry(mock_page, "https://example.com")

        assert result is True
        mock_page.wait_for_timeout.assert_called_once_with(2000)

    @pytest.mark.asyncio
    async def test_logs_warning_on_http_error(self, tmp_path):
        config = _make_config(tmp_path, wait_for_idle=False)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_page.goto = AsyncMock(return_value=mock_resp)

        result = await crawler._navigate_with_retry(mock_page, "https://example.com")

        # Still returns True (page loaded), even with server error
        assert result is True


class TestProcessPage:
    """Tests for Crawler._process_page."""

    @pytest.mark.asyncio
    async def test_extracts_page_info(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test Page")
        mock_page.content = AsyncMock(return_value="<html><body>Hello</body></html>")
        mock_page.screenshot = AsyncMock()

        with patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]) as mock_extract, \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]) as mock_forms:
            mock_page.evaluate = AsyncMock(return_value="static")

            page_model = await crawler._process_page(
                mock_page, "https://example.com/test", []
            )

        assert page_model.url == "https://example.com/test"
        assert page_model.title == "Test Page"
        assert page_model.page_id == _page_id("https://example.com/test")

    @pytest.mark.asyncio
    async def test_captures_screenshot(self, tmp_path):
        config = _make_config(tmp_path)
        output_dir = tmp_path / "out"
        crawler = Crawler(config, output_dir)

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test")
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.screenshot = AsyncMock()

        with patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]):
            mock_page.evaluate = AsyncMock(return_value="static")
            page_model = await crawler._process_page(
                mock_page, "https://example.com", []
            )

        assert page_model.screenshot_path != ""
        mock_page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_screenshot_failure_sets_empty_path(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test")
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.screenshot = AsyncMock(side_effect=RuntimeError("Browser crash"))

        with patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]):
            mock_page.evaluate = AsyncMock(return_value="static")
            page_model = await crawler._process_page(
                mock_page, "https://example.com", []
            )

        assert page_model.screenshot_path == ""

    @pytest.mark.asyncio
    async def test_dom_snapshot_saved(self, tmp_path):
        config = _make_config(tmp_path)
        output_dir = tmp_path / "out"
        crawler = Crawler(config, output_dir)

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test")
        mock_page.content = AsyncMock(return_value="<html><body>Snapshot</body></html>")
        mock_page.screenshot = AsyncMock()

        with patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]):
            mock_page.evaluate = AsyncMock(return_value="static")
            page_model = await crawler._process_page(
                mock_page, "https://example.com", []
            )

        assert page_model.dom_snapshot_path != ""
        assert Path(page_model.dom_snapshot_path).read_text() == "<html><body>Snapshot</body></html>"

    @pytest.mark.asyncio
    async def test_dom_snapshot_failure_sets_empty_path(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test")
        mock_page.content = AsyncMock(side_effect=RuntimeError("Detached"))
        mock_page.screenshot = AsyncMock()

        with patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]):
            mock_page.evaluate = AsyncMock(return_value="static")
            page_model = await crawler._process_page(
                mock_page, "https://example.com", []
            )

        assert page_model.dom_snapshot_path == ""

    @pytest.mark.asyncio
    async def test_title_failure_uses_empty_string(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(side_effect=RuntimeError("No page"))
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.screenshot = AsyncMock()

        with patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]):
            mock_page.evaluate = AsyncMock(return_value="static")
            page_model = await crawler._process_page(
                mock_page, "https://example.com", []
            )

        assert page_model.title == ""

    @pytest.mark.asyncio
    async def test_captures_network_requests(self, tmp_path):
        from src.models.site_model import NetworkRequest

        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test")
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.screenshot = AsyncMock()

        network_reqs = [
            NetworkRequest(url="https://example.com/api/data", method="GET",
                           resource_type="xhr", status=200),
        ]

        with patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]):
            mock_page.evaluate = AsyncMock(return_value="static")
            page_model = await crawler._process_page(
                mock_page, "https://example.com", network_reqs
            )

        assert len(page_model.network_requests) == 1
        assert page_model.network_requests[0].url == "https://example.com/api/data"


class TestClassifyPage:
    """Tests for Crawler._classify_page."""

    @pytest.mark.asyncio
    async def test_returns_evaluate_result(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="form")

        result = await crawler._classify_page(mock_page)
        assert result == "form"

    @pytest.mark.asyncio
    async def test_returns_static_on_error(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Detached"))

        result = await crawler._classify_page(mock_page)
        assert result == "static"


class TestAttachNetworkListener:
    """Tests for Crawler._attach_network_listener."""

    def test_registers_response_listener(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = Mock()
        nr_list = []

        crawler._attach_network_listener(mock_page, nr_list)

        mock_page.on.assert_called_once_with("response", mock_page.on.call_args[0][1])

    @pytest.mark.asyncio
    async def test_captures_xhr_as_api_endpoint(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        callbacks = {}
        mock_page = Mock()
        mock_page.on = Mock(side_effect=lambda event, cb: callbacks.update({event: cb}))

        nr_list = []
        crawler._attach_network_listener(mock_page, nr_list)

        # Simulate an XHR response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.request = Mock()
        mock_response.request.url = "https://example.com/api/users"
        mock_response.request.method = "GET"
        mock_response.request.resource_type = "xhr"

        await callbacks["response"](mock_response)

        assert len(nr_list) == 1
        assert nr_list[0].url == "https://example.com/api/users"
        assert "GET:/api/users" in crawler._api_endpoints
        assert crawler._api_endpoints["GET:/api/users"].method == "GET"

    @pytest.mark.asyncio
    async def test_tracks_multiple_status_codes(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        callbacks = {}
        mock_page = Mock()
        mock_page.on = Mock(side_effect=lambda event, cb: callbacks.update({event: cb}))

        nr_list = []
        crawler._attach_network_listener(mock_page, nr_list)

        for status in (200, 401):
            mock_response = Mock()
            mock_response.status = status
            mock_response.headers = {"content-type": "application/json"}
            mock_response.request = Mock()
            mock_response.request.url = "https://example.com/api/data"
            mock_response.request.method = "POST"
            mock_response.request.resource_type = "fetch"

            await callbacks["response"](mock_response)

        ep = crawler._api_endpoints["POST:/api/data"]
        assert 200 in ep.status_codes_seen
        assert 401 in ep.status_codes_seen


class TestExtractStaticLinks:
    """Tests for Crawler._extract_static_links."""

    @pytest.mark.asyncio
    async def test_returns_resolved_links(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            "https://example.com/about",
            "https://example.com/contact",
        ])

        links = await crawler._extract_static_links(mock_page, "https://example.com")

        assert "https://example.com/about" in links
        assert "https://example.com/contact" in links

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Detached"))

        links = await crawler._extract_static_links(mock_page, "https://example.com")

        assert links == set()


class TestExtractDynamicLinks:
    """Tests for Crawler._extract_dynamic_links."""

    @pytest.mark.asyncio
    async def test_returns_resolved_links(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            "/dashboard",
            "https://example.com/profile",
        ])

        links = await crawler._extract_dynamic_links(mock_page, "https://example.com")

        assert "https://example.com/dashboard" in links
        assert "https://example.com/profile" in links

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Detached"))

        links = await crawler._extract_dynamic_links(mock_page, "https://example.com")

        assert links == set()


class TestDiscoverInteractiveLinks:
    """Tests for Crawler._discover_interactive_links."""

    @pytest.mark.asyncio
    async def test_clicks_toggles_and_discovers_new_links(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.url = "https://example.com"

        # First evaluate: _get_visible_link_hrefs (before)
        # Then evaluate: find toggles
        # Then evaluate: _get_visible_link_hrefs (after)
        links_before = ["https://example.com/home"]
        links_after = ["https://example.com/home", "https://example.com/hidden-page"]
        toggles = ["#menu-btn"]

        evaluate_calls = [
            links_before,  # _get_visible_link_hrefs before
            toggles,       # find toggle elements
        ]

        call_count = 0
        async def evaluate_side_effect(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            if idx < len(evaluate_calls):
                return evaluate_calls[idx]
            return links_after  # subsequent calls are _get_visible_link_hrefs after

        mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)

        mock_el = AsyncMock()
        mock_el.is_visible = AsyncMock(return_value=True)
        mock_el.click = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_el)
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.keyboard = AsyncMock()
        mock_page.keyboard.press = AsyncMock()

        links = await crawler._discover_interactive_links(mock_page, "https://example.com")

        assert "https://example.com/hidden-page" in links

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Detached"))

        links = await crawler._discover_interactive_links(mock_page, "https://example.com")

        assert links == set()


class TestLoadSitemapBackfill:
    """Tests for Crawler._load_sitemap_backfill."""

    @pytest.mark.asyncio
    async def test_loads_sitemap_urls(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        sitemap_content = """<?xml version="1.0"?>
        <urlset>
            <url><loc>https://example.com/page1</loc></url>
            <url><loc>https://example.com/page2</loc></url>
            <url><loc>https://example.com/image.png</loc></url>
        </urlset>"""

        mock_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_page.goto = AsyncMock(return_value=mock_resp)
        mock_page.content = AsyncMock(return_value=sitemap_content)
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        heap = []
        count = await crawler._load_sitemap_backfill(
            mock_context, "https://example.com", heap
        )

        # 2 valid page URLs (image.png is filtered out)
        assert count == 2
        assert len(heap) == 2

    @pytest.mark.asyncio
    async def test_returns_zero_on_missing_sitemap(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_page.goto = AsyncMock(return_value=mock_resp)
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        heap = []
        count = await crawler._load_sitemap_backfill(
            mock_context, "https://example.com", heap
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_handles_sitemap_error(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=RuntimeError("Network error"))
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        heap = []
        count = await crawler._load_sitemap_backfill(
            mock_context, "https://example.com", heap
        )

        assert count == 0


class TestProbeAuthRequirements:
    """Tests for Crawler._probe_auth_requirements."""

    @pytest.mark.asyncio
    async def test_marks_401_as_auth_required(self, tmp_path):
        from src.models.config import AuthConfig
        from src.models.site_model import PageModel

        config = _make_config(tmp_path)
        config.auth = AuthConfig(
            login_url="https://example.com/login",
            username="user", password="pass",
        )
        crawler = Crawler(config, tmp_path / "out")
        crawler._pages = [PageModel(page_id="p1", url="https://example.com/dashboard")]

        mock_probe_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 401
        mock_probe_page.goto = AsyncMock(return_value=mock_resp)
        mock_probe_page.url = "https://example.com/dashboard"
        mock_probe_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_probe_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await crawler._probe_auth_requirements(mock_browser)

        assert crawler._pages[0].auth_required is True

    @pytest.mark.asyncio
    async def test_marks_redirect_to_login_as_auth_required(self, tmp_path):
        from src.models.config import AuthConfig
        from src.models.site_model import PageModel

        config = _make_config(tmp_path)
        config.auth = AuthConfig(
            login_url="https://example.com/login",
            username="user", password="pass",
        )
        crawler = Crawler(config, tmp_path / "out")
        crawler._pages = [PageModel(page_id="p1", url="https://example.com/dashboard")]

        mock_probe_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 302
        mock_probe_page.goto = AsyncMock(return_value=mock_resp)
        mock_probe_page.url = "https://example.com/login?next=/dashboard"
        mock_probe_page.title = AsyncMock(return_value="Login")
        mock_probe_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_probe_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await crawler._probe_auth_requirements(mock_browser)

        assert crawler._pages[0].auth_required is True

    @pytest.mark.asyncio
    async def test_marks_public_page(self, tmp_path):
        from src.models.config import AuthConfig
        from src.models.site_model import PageModel

        config = _make_config(tmp_path)
        config.auth = AuthConfig(
            login_url="https://example.com/login",
            username="user", password="pass",
        )
        crawler = Crawler(config, tmp_path / "out")
        crawler._pages = [PageModel(page_id="p1", url="https://example.com/about")]

        mock_probe_page = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_probe_page.goto = AsyncMock(return_value=mock_resp)
        mock_probe_page.url = "https://example.com/about"
        mock_probe_page.title = AsyncMock(return_value="About Us")
        mock_probe_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_probe_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await crawler._probe_auth_requirements(mock_browser)

        assert crawler._pages[0].auth_required is False

    @pytest.mark.asyncio
    async def test_marks_unknown_on_probe_error(self, tmp_path):
        from src.models.config import AuthConfig
        from src.models.site_model import PageModel

        config = _make_config(tmp_path)
        config.auth = AuthConfig(
            login_url="https://example.com/login",
            username="user", password="pass",
        )
        crawler = Crawler(config, tmp_path / "out")
        crawler._pages = [PageModel(page_id="p1", url="https://example.com/broken")]

        mock_probe_page = AsyncMock()
        mock_probe_page.goto = AsyncMock(side_effect=RuntimeError("Network error"))
        mock_probe_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_probe_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        await crawler._probe_auth_requirements(mock_browser)

        assert crawler._pages[0].auth_required is None

    @pytest.mark.asyncio
    async def test_skips_when_no_pages(self, tmp_path):
        config = _make_config(tmp_path)
        crawler = Crawler(config, tmp_path / "out")
        crawler._pages = []

        mock_browser = AsyncMock()
        await crawler._probe_auth_requirements(mock_browser)

        # Should return early without calling new_context
        mock_browser.new_context.assert_not_called()


# ============================================================================
# Element extractor tests
# ============================================================================


class TestExtractElements:
    """Tests for extract_elements."""

    @pytest.mark.asyncio
    async def test_extracts_elements_from_page(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                "tag": "button",
                "selector": "#submit",
                "role": "button",
                "text_content": "Submit",
                "is_interactive": True,
                "element_type": "button",
                "attributes": {"id": "submit", "type": "submit"},
            },
            {
                "tag": "a",
                "selector": "a.nav-link",
                "role": "link",
                "text_content": "Home",
                "is_interactive": True,
                "element_type": "link",
                "attributes": {"href": "/home"},
            },
        ])

        elements = await extract_elements(mock_page)

        assert len(elements) == 2
        assert isinstance(elements[0], ElementModel)
        assert elements[0].tag == "button"
        assert elements[0].selector == "#submit"
        assert elements[0].role == "button"
        assert elements[0].text_content == "Submit"
        assert elements[1].tag == "a"
        assert elements[1].element_type == "link"

    @pytest.mark.asyncio
    async def test_generates_element_ids(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                "tag": "input",
                "selector": "input[name='email']",
                "role": "textbox",
                "text_content": "",
                "is_interactive": True,
                "element_type": "input",
                "attributes": {"name": "email", "type": "email"},
            },
        ])

        elements = await extract_elements(mock_page)

        assert len(elements) == 1
        assert len(elements[0].element_id) == 10  # md5[:10]
        assert all(c in "0123456789abcdef" for c in elements[0].element_id)

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Browser crashed"))

        elements = await extract_elements(mock_page)

        assert elements == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_page(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])

        elements = await extract_elements(mock_page)

        assert elements == []

    @pytest.mark.asyncio
    async def test_handles_missing_attributes(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                "tag": "div",
                "selector": "div.clickable",
                # Missing optional fields
            },
        ])

        elements = await extract_elements(mock_page)

        assert len(elements) == 1
        assert elements[0].tag == "div"
        assert elements[0].role == ""
        assert elements[0].text_content == ""


# ============================================================================
# Form analyzer tests
# ============================================================================


class TestAnalyzeForms:
    """Tests for analyze_forms."""

    @pytest.mark.asyncio
    async def test_analyzes_forms_from_page(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                "action": "https://example.com/api/login",
                "method": "POST",
                "fields": [
                    {
                        "name": "email",
                        "field_type": "email",
                        "required": True,
                        "validation_pattern": None,
                        "options": None,
                        "selector": "#email",
                    },
                    {
                        "name": "password",
                        "field_type": "password",
                        "required": True,
                        "validation_pattern": None,
                        "options": None,
                        "selector": "#password",
                    },
                ],
                "submit_selector": "button[type='submit']",
            },
        ])

        forms = await analyze_forms(mock_page)

        assert len(forms) == 1
        assert isinstance(forms[0], FormModel)
        assert forms[0].action == "https://example.com/api/login"
        assert forms[0].method == "POST"
        assert len(forms[0].fields) == 2
        assert forms[0].fields[0].name == "email"
        assert forms[0].fields[0].field_type == "email"
        assert forms[0].fields[0].required is True
        assert forms[0].fields[1].name == "password"
        assert forms[0].submit_selector == "button[type='submit']"

    @pytest.mark.asyncio
    async def test_generates_form_ids(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {"action": "/search", "method": "GET", "fields": [], "submit_selector": ""},
            {"action": "/login", "method": "POST", "fields": [], "submit_selector": ""},
        ])

        forms = await analyze_forms(mock_page)

        assert len(forms) == 2
        assert forms[0].form_id != forms[1].form_id
        assert len(forms[0].form_id) == 10

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Browser crashed"))

        forms = await analyze_forms(mock_page)

        assert forms == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_forms(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])

        forms = await analyze_forms(mock_page)

        assert forms == []

    @pytest.mark.asyncio
    async def test_form_with_select_options(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                "action": "/filter",
                "method": "GET",
                "fields": [
                    {
                        "name": "category",
                        "field_type": "select",
                        "required": False,
                        "validation_pattern": None,
                        "options": ["electronics", "clothing", "books"],
                        "selector": "select[name='category']",
                    },
                ],
                "submit_selector": "",
            },
        ])

        forms = await analyze_forms(mock_page)

        assert len(forms) == 1
        assert forms[0].fields[0].field_type == "select"
        assert forms[0].fields[0].options == ["electronics", "clothing", "books"]


# ============================================================================
# SPA handler tests
# ============================================================================


class TestDetectSpaType:
    """Tests for detect_spa_type."""

    @pytest.mark.asyncio
    async def test_detects_traditional(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={
            "is_spa": False,
            "framework": "unknown",
            "routing_type": "traditional",
        })

        result = await detect_spa_type(mock_page)
        assert result == "traditional"

    @pytest.mark.asyncio
    async def test_detects_hash_routing(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={
            "is_spa": True,
            "framework": "vue",
            "routing_type": "hash",
        })

        result = await detect_spa_type(mock_page)
        assert result == "hash"

    @pytest.mark.asyncio
    async def test_detects_history_routing(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={
            "is_spa": True,
            "framework": "react",
            "routing_type": "history",
        })

        result = await detect_spa_type(mock_page)
        assert result == "history"

    @pytest.mark.asyncio
    async def test_returns_traditional_on_error(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Detached"))

        result = await detect_spa_type(mock_page)
        assert result == "traditional"

    @pytest.mark.asyncio
    async def test_returns_traditional_on_missing_key(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={})

        result = await detect_spa_type(mock_page)
        assert result == "traditional"


class TestDiscoverSpaRoutes:
    """Tests for discover_spa_routes."""

    @pytest.mark.asyncio
    async def test_discovers_relative_routes(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            "/dashboard",
            "/settings",
            "/profile",
        ])

        routes = await discover_spa_routes(mock_page, "https://example.com")

        assert len(routes) == 3
        assert "https://example.com/dashboard" in routes
        assert "https://example.com/settings" in routes
        assert "https://example.com/profile" in routes

    @pytest.mark.asyncio
    async def test_discovers_hash_routes(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            "#/home",
            "#/about",
        ])

        routes = await discover_spa_routes(mock_page, "https://example.com")

        assert len(routes) == 2
        assert "https://example.com#/home" in routes
        assert "https://example.com#/about" in routes

    @pytest.mark.asyncio
    async def test_ignores_non_route_hrefs(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            "/dashboard",
            "https://external.com/link",  # not relative or hash
        ])

        routes = await discover_spa_routes(mock_page, "https://example.com")

        # External absolute links are skipped (not starting with / or #/)
        assert len(routes) == 1
        assert "https://example.com/dashboard" in routes

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=RuntimeError("Detached"))

        routes = await discover_spa_routes(mock_page, "https://example.com")

        assert routes == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_routes(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])

        routes = await discover_spa_routes(mock_page, "https://example.com")

        assert routes == []

    @pytest.mark.asyncio
    async def test_deduplicates_routes(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            "/dashboard",
            "/dashboard",  # duplicate
        ])

        routes = await discover_spa_routes(mock_page, "https://example.com")

        assert len(routes) == 1


# ============================================================================
# Integration-style: Crawler.crawl()
# ============================================================================


class TestCrawlerCrawlIntegration:
    """Higher-level tests for the full crawl() method."""

    @pytest.mark.asyncio
    async def test_crawl_returns_site_model(self, tmp_path):
        config = _make_config(tmp_path, max_pages=1, wait_for_idle=False)
        crawler = Crawler(config, tmp_path / "out")

        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.on = Mock()  # Sync callback registration
        mock_page.close = AsyncMock()

        # goto returns a 200 response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_page.goto = AsyncMock(return_value=mock_resp)
        mock_page.title = AsyncMock(return_value="Example")
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.screenshot = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        # evaluate calls: _classify_page returns a string, link discovery returns lists
        # Use side_effect to return "static" for classify, [] for link discovery
        def evaluate_side_effect(js_code, *args, **kwargs):
            if "return 'error'" in js_code or "return 'form'" in js_code:
                # _classify_page JS
                return "static"
            return []
        mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()

        with patch("src.crawler.crawler.async_playwright") as mock_pw, \
             patch("src.crawler.crawler.launch_stealth_browser", return_value=mock_browser), \
             patch("src.crawler.crawler.create_stealth_context", return_value=mock_context), \
             patch("src.crawler.crawler.extract_elements", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.analyze_forms", new_callable=AsyncMock, return_value=[]), \
             patch("src.crawler.crawler.detect_spa_type", new_callable=AsyncMock, return_value="traditional"), \
             patch("src.crawler.crawler.human_delay", new_callable=AsyncMock):

            mock_pw.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            # Sitemap page returns 404
            mock_sitemap_page = AsyncMock()
            mock_sitemap_resp = AsyncMock()
            mock_sitemap_resp.status = 404
            mock_sitemap_page.goto = AsyncMock(return_value=mock_sitemap_resp)
            mock_sitemap_page.close = AsyncMock()

            # First new_page call is for crawl, second for sitemap
            mock_context.new_page = AsyncMock(side_effect=[mock_page, mock_sitemap_page])

            site_model = await crawler.crawl()

        assert site_model.base_url == "https://example.com"
        assert len(site_model.pages) == 1
        assert site_model.pages[0].title == "Example"
        assert site_model.crawl_metadata["pages_found"] == 1
        assert site_model.crawl_metadata["is_spa"] is False
