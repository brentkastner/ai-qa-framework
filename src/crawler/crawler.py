"""Site crawler — discovers pages, elements, forms, and navigation structure."""

from __future__ import annotations

import asyncio
import hashlib
import heapq
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

from src.models.config import FrameworkConfig
from src.auth.smart_auth import perform_smart_auth
from src.models.site_model import (
    APIEndpoint,
    NetworkRequest,
    PageModel,
    SiteModel,
)

from .element_extractor import extract_elements
from .form_analyzer import analyze_forms
from .spa_handler import detect_spa_type, discover_spa_routes

logger = logging.getLogger(__name__)

# Priority constants — lower number = higher priority (processed first)
PRIORITY_START = 0        # The start URL
PRIORITY_ORGANIC = 10     # Links discovered by crawling real pages
PRIORITY_INTERACTIVE = 20 # Links found by clicking menus/dropdowns
PRIORITY_SITEMAP = 50     # Links from sitemap.xml (backfill)


def _normalize_url(url: str) -> str:
    """Normalize a URL for deduplication."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    query = ""
    if parsed.query:
        params = sorted(parsed.query.split("&"))
        query = "?" + "&".join(params)
    return f"{parsed.scheme}://{parsed.netloc}{path}{query}"


def _page_id(url: str) -> str:
    """Generate a stable page ID from the normalized URL."""
    return hashlib.md5(_normalize_url(url).encode()).hexdigest()[:12]


def _is_same_origin(base_url: str, candidate_url: str) -> bool:
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def _is_valid_page_url(url: str) -> bool:
    """Filter out non-page URLs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    skip_extensions = (
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
        '.css', '.js', '.map', '.woff', '.woff2', '.ttf', '.eot',
        '.pdf', '.zip', '.tar', '.gz', '.mp3', '.mp4', '.webm',
        '.xml', '.rss', '.atom', '.json',
    )
    path_lower = parsed.path.lower()
    return not any(path_lower.endswith(ext) for ext in skip_extensions)


def _matches_patterns(url: str, patterns: list[str]) -> bool:
    return any(re.search(p, url) for p in patterns)


class _CrawlEntry:
    """Priority queue entry for crawl URLs. Lower priority = processed first."""
    _counter = 0

    def __init__(self, url: str, depth: int, priority: int):
        self.url = url
        self.depth = depth
        self.priority = priority
        # Counter ensures FIFO ordering within same priority level
        _CrawlEntry._counter += 1
        self._order = _CrawlEntry._counter

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self._order < other._order


class Crawler:
    """Crawls a website using Playwright and builds a SiteModel.

    Uses a priority queue to ensure links found by actually visiting pages
    are crawled before sitemap-only URLs. The crawl loop:

    1. Visits a page in the browser
    2. Extracts links from the rendered DOM (static, dynamic, interactive)
    3. Queues discovered links at HIGH priority (organic discovery)
    4. Sitemap URLs sit in the queue at LOW priority as backfill
    5. Repeat until page budget is exhausted

    Link discovery sources:
    - <a href>, <area href>, <frame src> elements
    - SPA router links (hash-based and history-based routing)
    - onclick handlers, data-href/data-url attributes
    - Hidden links revealed by clicking nav menus and dropdowns
    - sitemap.xml (low-priority backfill)
    """

    def __init__(self, config: FrameworkConfig, output_dir: Path, ai_client=None):
        self.config = config
        self.crawl_config = config.crawl
        self.output_dir = output_dir
        self.baselines_dir = output_dir / "baselines"
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        self._ai_client = ai_client

        self._visited_urls: set[str] = set()
        self._queued_urls: set[str] = set()
        self._pages: list[PageModel] = []
        self._nav_graph: dict[str, list[str]] = {}
        self._api_endpoints: dict[str, APIEndpoint] = {}
        self._is_spa: bool = False

    async def crawl(self) -> SiteModel:
        """Execute the crawl and return a SiteModel."""
        start_time = time.time()
        target = self.crawl_config.target_url
        logger.info("Starting crawl of %s", target)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={
                    "width": self.crawl_config.viewport.width,
                    "height": self.crawl_config.viewport.height,
                },
                user_agent=self.crawl_config.user_agent,
            )

            auth_flow = None
            if self.config.auth:
                result = await perform_smart_auth(
                    context, self.config.auth, ai_client=self._ai_client,
                )
                if result.success:
                    auth_flow = result.auth_flow
                else:
                    logger.error("Authentication failed: %s", result.error)

            await self._priority_crawl(context, target)

            # Probe auth requirements for each discovered page
            if self.config.auth and auth_flow:
                await self._probe_auth_requirements(browser)
            else:
                for page_model in self._pages:
                    page_model.auth_required = False

            await browser.close()

        duration = time.time() - start_time
        logger.info(
            "Crawl complete: %d pages discovered in %.1fs",
            len(self._pages), duration,
        )

        return SiteModel(
            base_url=target,
            pages=self._pages,
            navigation_graph=self._nav_graph,
            api_endpoints=list(self._api_endpoints.values()),
            auth_flow=auth_flow,
            crawl_metadata={
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duration_seconds": round(duration, 2),
                "pages_found": len(self._pages),
                "is_spa": self._is_spa,
            },
        )

    async def _probe_auth_requirements(self, browser) -> None:
        """Probe each discovered page in a clean context to determine if auth is required."""
        if not self._pages:
            return
        logger.info("Probing %d pages for auth requirements", len(self._pages))
        clean_context = await browser.new_context(
            viewport={
                "width": self.crawl_config.viewport.width,
                "height": self.crawl_config.viewport.height,
            },
            user_agent=self.crawl_config.user_agent,
        )
        probe_page = await clean_context.new_page()

        login_path = ""
        if self.config.auth and self.config.auth.login_url:
            login_path = urlparse(self.config.auth.login_url).path.rstrip("/")

        for page_model in self._pages:
            try:
                resp = await probe_page.goto(
                    page_model.url, wait_until="domcontentloaded", timeout=10000,
                )
                if resp is None:
                    page_model.auth_required = True
                    continue

                status = resp.status
                final_url = probe_page.url

                # HTTP 401/403 → requires auth
                if status in (401, 403):
                    page_model.auth_required = True
                # Redirected to login URL
                elif login_path and login_path in urlparse(final_url).path:
                    page_model.auth_required = True
                else:
                    # Check if landing page looks like a login form
                    title = (await probe_page.title() or "").lower()
                    if any(kw in title for kw in ("login", "sign in", "log in", "authenticate")):
                        page_model.auth_required = True
                    else:
                        page_model.auth_required = False

            except Exception as e:
                logger.debug("Auth probe failed for %s: %s", page_model.url, e)
                page_model.auth_required = None

        await probe_page.close()
        await clean_context.close()
        auth_count = sum(1 for p in self._pages if p.auth_required is True)
        public_count = sum(1 for p in self._pages if p.auth_required is False)
        logger.info("Auth probe: %d require auth, %d public", auth_count, public_count)

    # ------------------------------------------------------------------
    # Core crawl loop
    # ------------------------------------------------------------------

    async def _priority_crawl(self, context: BrowserContext, start_url: str) -> None:
        """Priority-based crawl: organic links first, sitemap as backfill."""
        heap: list[_CrawlEntry] = []

        # Queue the start URL at highest priority
        self._enqueue(heap, start_url, depth=0, priority=PRIORITY_START)

        # Open a single page we'll reuse for the entire crawl
        page = await context.new_page()
        network_requests: list[NetworkRequest] = []
        self._attach_network_listener(page, network_requests)

        # Track whether we've loaded the sitemap yet (defer until after first page)
        sitemap_loaded = False

        while heap and len(self._visited_urls) < self.crawl_config.max_pages:
            entry = heapq.heappop(heap)
            url = entry.url
            depth = entry.depth
            normalized = _normalize_url(url)

            if normalized in self._visited_urls:
                continue
            if depth > self.crawl_config.max_depth:
                continue
            if not self._url_in_scope(url):
                continue

            self._visited_urls.add(normalized)
            logger.info(
                "Crawling [%d/%d] depth=%d prio=%d: %s",
                len(self._visited_urls), self.crawl_config.max_pages,
                depth, entry.priority, url,
            )

            network_requests.clear()

            try:
                loaded = await self._navigate_with_retry(page, url)
                if not loaded:
                    logger.warning("Failed to load: %s", url)
                    continue

                # Detect SPA on first page
                if len(self._visited_urls) == 1:
                    spa_type = await detect_spa_type(page)
                    self._is_spa = spa_type != "traditional"
                    if self._is_spa:
                        logger.info("SPA detected (routing: %s)", spa_type)

                # Process page content
                page_model = await self._process_page(page, url, network_requests)
                self._pages.append(page_model)

                # === LINK DISCOVERY ===
                discovered = await self._discover_all_links(page, url)

                # Build nav graph and queue discovered links at ORGANIC priority
                pid = page_model.page_id
                self._nav_graph[pid] = []
                organic_count = 0
                for link_url in discovered:
                    if not _is_valid_page_url(link_url):
                        continue
                    if not _is_same_origin(self.crawl_config.target_url, link_url):
                        continue

                    link_id = _page_id(link_url)
                    self._nav_graph[pid].append(link_id)

                    if self._enqueue(heap, link_url, depth + 1, PRIORITY_ORGANIC):
                        organic_count += 1

                logger.info(
                    "Page '%s' — %d links found, %d new queued",
                    page_model.title or url, len(discovered), organic_count,
                )

                # After the first page is processed, load sitemap as backfill
                if not sitemap_loaded:
                    sitemap_loaded = True
                    sitemap_count = await self._load_sitemap_backfill(
                        context, start_url, heap
                    )
                    if sitemap_count:
                        logger.info("Sitemap backfill: %d URLs queued", sitemap_count)

            except Exception as e:
                logger.error("Error crawling %s: %s", url, e)

        await page.close()

        logger.info(
            "Crawl finished: %d pages visited, %d total URLs seen",
            len(self._visited_urls), len(self._queued_urls),
        )

    def _enqueue(
        self, heap: list[_CrawlEntry], url: str, depth: int, priority: int
    ) -> bool:
        """Add a URL to the crawl queue if not already seen. Returns True if newly queued."""
        normalized = _normalize_url(url)
        if normalized in self._visited_urls or normalized in self._queued_urls:
            return False
        if not self._url_in_scope(url):
            return False

        self._queued_urls.add(normalized)
        heapq.heappush(heap, _CrawlEntry(url, depth, priority))
        return True

    def _url_in_scope(self, url: str) -> bool:
        if not _is_same_origin(self.crawl_config.target_url, url):
            return False
        if self.crawl_config.exclude_patterns and _matches_patterns(
            url, self.crawl_config.exclude_patterns
        ):
            return False
        if self.crawl_config.include_patterns and not _matches_patterns(
            url, self.crawl_config.include_patterns
        ):
            return False
        return True

    # ------------------------------------------------------------------
    # Page processing
    # ------------------------------------------------------------------

    async def _process_page(
        self, page: Page, url: str, network_requests: list[NetworkRequest]
    ) -> PageModel:
        """Extract all information from a loaded page."""
        title = ""
        try:
            title = await page.title() or ""
        except Exception:
            pass

        page_type = await self._classify_page(page)
        elements = await extract_elements(page)
        forms = await analyze_forms(page)

        pid = _page_id(url)
        screenshot_path = ""
        try:
            screenshot_path = str(self.baselines_dir / f"{pid}_screenshot.png")
            await page.screenshot(path=screenshot_path, full_page=True)
        except Exception as e:
            logger.debug("Screenshot failed for %s: %s", url, e)
            screenshot_path = ""

        dom_path = ""
        try:
            dom_path = str(self.baselines_dir / f"{pid}_dom.html")
            dom_content = await page.content()
            with open(dom_path, "w", encoding="utf-8") as f:
                f.write(dom_content)
        except Exception as e:
            logger.debug("DOM snapshot failed for %s: %s", url, e)
            dom_path = ""

        return PageModel(
            page_id=pid,
            url=url,
            page_type=page_type,
            title=title,
            elements=elements,
            forms=forms,
            network_requests=list(network_requests),
            screenshot_path=screenshot_path,
            dom_snapshot_path=dom_path,
        )

    # ------------------------------------------------------------------
    # Link discovery (multiple strategies)
    # ------------------------------------------------------------------

    async def _discover_all_links(self, page: Page, base_url: str) -> set[str]:
        """Run all link discovery strategies and return the union of results."""
        discovered = set()

        # 1. Static DOM links (<a>, <area>, <frame>, <iframe>)
        static = await self._extract_static_links(page, base_url)
        discovered.update(static)

        # 2. SPA route links
        if self._is_spa:
            try:
                spa = await discover_spa_routes(page, base_url)
                discovered.update(spa)
            except Exception as e:
                logger.debug("SPA route discovery error: %s", e)

        # 3. Dynamic links (onclick, data attributes, meta refresh)
        dynamic = await self._extract_dynamic_links(page, base_url)
        discovered.update(dynamic)

        # 4. Interactive links (click menus/dropdowns to reveal hidden nav)
        interactive = await self._discover_interactive_links(page, base_url)
        discovered.update(interactive)

        logger.debug(
            "Link discovery for %s: %d static, %d dynamic, %d interactive, %d total unique",
            base_url, len(static), len(dynamic), len(interactive), len(discovered),
        )
        return discovered

    async def _extract_static_links(self, page: Page, base_url: str) -> set[str]:
        """Extract links from <a href>, <area href>, frame/iframe src."""
        try:
            hrefs = await page.evaluate("""() => {
                const results = [];

                // Standard anchor links
                document.querySelectorAll('a[href]').forEach(el => {
                    results.push(el.href);
                });

                // Image map area links
                document.querySelectorAll('area[href]').forEach(el => {
                    results.push(el.href);
                });

                // Frames / iframes
                document.querySelectorAll('frame[src], iframe[src]').forEach(el => {
                    if (el.src) results.push(el.src);
                });

                return results.filter(h =>
                    h &&
                    !h.startsWith('javascript:') &&
                    !h.startsWith('mailto:') &&
                    !h.startsWith('tel:') &&
                    !h.startsWith('data:') &&
                    !h.startsWith('blob:')
                );
            }""")
            return self._resolve_urls(hrefs, base_url)
        except Exception as e:
            logger.debug("Static link extraction failed: %s", e)
            return set()

    async def _extract_dynamic_links(self, page: Page, base_url: str) -> set[str]:
        """Extract URLs from onclick, data attributes, formaction, meta refresh."""
        try:
            urls = await page.evaluate("""() => {
                const results = [];

                // onclick handlers — extract URL patterns
                document.querySelectorAll('[onclick]').forEach(el => {
                    const onclick = el.getAttribute('onclick') || '';
                    const locMatch = onclick.match(
                        /(?:window\\.)?location(?:\\.href)?\\s*=\\s*["']([^"']+)["']/
                    );
                    if (locMatch) results.push(locMatch[1]);
                    const navMatch = onclick.match(
                        /(?:navigate|goto|redirect|router\\.push)\\s*\\(?\\s*["']([^"']+)["']/i
                    );
                    if (navMatch) results.push(navMatch[1]);
                });

                // data-href, data-url, data-link, data-to, data-route
                const dataAttrs = ['data-href', 'data-url', 'data-link', 'data-to', 'data-route'];
                for (const attr of dataAttrs) {
                    document.querySelectorAll(`[${attr}]`).forEach(el => {
                        const val = el.getAttribute(attr);
                        if (val && (val.startsWith('/') || val.startsWith('http'))) {
                            results.push(val);
                        }
                    });
                }

                // Buttons with formaction
                document.querySelectorAll('button[formaction], input[formaction]').forEach(el => {
                    const val = el.getAttribute('formaction');
                    if (val) results.push(val);
                });

                // Meta refresh
                document.querySelectorAll('meta[http-equiv="refresh"]').forEach(el => {
                    const content = el.getAttribute('content') || '';
                    const match = content.match(/url\\s*=\\s*["']?([^"';\\s]+)/i);
                    if (match) results.push(match[1]);
                });

                // Form actions
                document.querySelectorAll('form[action]').forEach(el => {
                    const action = el.getAttribute('action');
                    if (action && action !== '#' && !action.startsWith('javascript:')) {
                        results.push(action);
                    }
                });

                return results.filter(r => r && !r.startsWith('javascript:'));
            }""")
            return self._resolve_urls(urls, base_url)
        except Exception as e:
            logger.debug("Dynamic link extraction failed: %s", e)
            return set()

    async def _discover_interactive_links(self, page: Page, base_url: str) -> set[str]:
        """Click nav menus, dropdowns, hamburger buttons to reveal hidden links."""
        discovered = set()

        try:
            # Collect all currently-visible links BEFORE interaction
            links_before = await self._get_visible_link_hrefs(page)

            # Find navigation toggle elements
            toggles = await page.evaluate("""() => {
                const selectors = [];
                const candidates = document.querySelectorAll(
                    'nav button, nav [role="button"], ' +
                    '[class*="menu-toggle"], [class*="hamburger"], [class*="nav-toggle"], ' +
                    '[class*="dropdown-toggle"], [aria-haspopup="true"], ' +
                    '[data-toggle="dropdown"], [data-bs-toggle="dropdown"], ' +
                    'button[aria-expanded="false"], [class*="navbar-toggler"], ' +
                    'details > summary'
                );
                for (const el of candidates) {
                    if (el.offsetParent === null && !el.closest('details')) continue;
                    let sel = '';
                    if (el.id) sel = '#' + CSS.escape(el.id);
                    else if (el.getAttribute('aria-label'))
                        sel = `[aria-label="${el.getAttribute('aria-label')}"]`;
                    else if (el.className && typeof el.className === 'string') {
                        const cls = el.className.trim().split(/\\s+/)[0];
                        if (cls) sel = el.tagName.toLowerCase() + '.' + CSS.escape(cls);
                    }
                    if (sel) selectors.push(sel);
                }
                return selectors.slice(0, 8);
            }""")

            original_url = page.url

            for selector in toggles:
                try:
                    el = await page.query_selector(selector)
                    if not el or not await el.is_visible():
                        continue

                    await el.click(timeout=3000)
                    await page.wait_for_timeout(500)

                    # Collect links AFTER clicking
                    links_after = await self._get_visible_link_hrefs(page)
                    new_links = links_after - links_before
                    discovered.update(self._resolve_urls(list(new_links), base_url))

                    # Close menu
                    try:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass

                except Exception as e:
                    logger.debug("Interactive click failed (%s): %s", selector, e)

            # Restore original page if we navigated away
            if page.url != original_url:
                try:
                    await page.goto(original_url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass

        except Exception as e:
            logger.debug("Interactive link discovery error: %s", e)

        return discovered

    async def _get_visible_link_hrefs(self, page: Page) -> set[str]:
        """Get hrefs of all currently visible links on the page."""
        try:
            hrefs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const rect = a.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    })
                    .map(a => a.href)
                    .filter(h =>
                        h && !h.startsWith('javascript:') &&
                        !h.startsWith('mailto:') && !h.startsWith('tel:')
                    );
            }""")
            return set(hrefs)
        except Exception:
            return set()

    # ------------------------------------------------------------------
    # Sitemap backfill
    # ------------------------------------------------------------------

    async def _load_sitemap_backfill(
        self, context: BrowserContext, start_url: str, heap: list[_CrawlEntry]
    ) -> int:
        """Fetch sitemap.xml and add URLs as low-priority backfill."""
        parsed = urlparse(start_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        count = 0

        page = await context.new_page()
        try:
            resp = await page.goto(sitemap_url, wait_until="domcontentloaded", timeout=10000)
            if resp and resp.status == 200:
                content = await page.content()
                loc_matches = re.findall(r'<loc>\s*(https?://[^<\s]+)\s*</loc>', content)
                for loc_url in loc_matches:
                    if _is_valid_page_url(loc_url):
                        if self._enqueue(heap, loc_url, depth=1, priority=PRIORITY_SITEMAP):
                            count += 1
        except Exception:
            logger.debug("No sitemap.xml found or failed to parse")
        finally:
            await page.close()

        return count

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def _navigate_with_retry(self, page: Page, url: str, retries: int = 2) -> bool:
        """Navigate to a URL with retry on failure."""
        for attempt in range(retries + 1):
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if resp and resp.status >= 400 and resp.status != 404:
                    logger.warning("HTTP %d for %s", resp.status, url)

                if self.crawl_config.wait_for_idle:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        await page.wait_for_timeout(2000)

                return True
            except Exception as e:
                if attempt < retries:
                    logger.debug("Retry %d for %s: %s", attempt + 1, url, e)
                    await asyncio.sleep(1)
                else:
                    logger.warning("Navigation failed after %d retries: %s — %s", retries, url, e)
                    return False
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_urls(self, hrefs: list[str], base_url: str) -> set[str]:
        """Resolve a list of hrefs to absolute, deduplicated, valid URLs."""
        resolved = set()
        for href in hrefs:
            try:
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.query:
                    clean += f"?{parsed.query}"
                if _is_valid_page_url(clean):
                    resolved.add(clean)
            except Exception:
                pass
        return resolved

    def _attach_network_listener(
        self, page: Page, nr_list: list[NetworkRequest]
    ) -> None:
        """Attach a network response listener to a page."""
        async def on_response(response):
            try:
                req = response.request
                nr_list.append(NetworkRequest(
                    url=req.url,
                    method=req.method,
                    resource_type=req.resource_type,
                    status=response.status,
                    content_type=response.headers.get("content-type", ""),
                ))
                if req.resource_type in ("xhr", "fetch"):
                    key = f"{req.method}:{urlparse(req.url).path}"
                    if key not in self._api_endpoints:
                        self._api_endpoints[key] = APIEndpoint(
                            url=req.url,
                            method=req.method,
                            response_content_type=response.headers.get("content-type"),
                            status_codes_seen=[response.status],
                        )
                    else:
                        ep = self._api_endpoints[key]
                        if response.status not in ep.status_codes_seen:
                            ep.status_codes_seen.append(response.status)
            except Exception:
                pass

        page.on("response", on_response)

    async def _classify_page(self, page: Page) -> str:
        """Classify a page based on its content and structure."""
        try:
            return await page.evaluate("""() => {
                const forms = document.querySelectorAll('form');
                const inputs = document.querySelectorAll('input, textarea, select');
                const dashWidgets = document.querySelectorAll(
                    '[class*="dashboard"], [class*="widget"], [class*="chart"], [class*="metric"]'
                );
                const errorInd = document.querySelectorAll(
                    '[class*="error"], [class*="404"], [class*="not-found"]'
                );
                const title = document.title.toLowerCase();
                const h1 = (document.querySelector('h1')?.textContent || '').toLowerCase();

                if (errorInd.length > 0 || title.includes('404') || title.includes('error') ||
                    h1.includes('not found') || h1.includes('page not found'))
                    return 'error';
                if (forms.length > 0 && inputs.length >= 3)
                    return 'form';
                if (dashWidgets.length > 0)
                    return 'dashboard';
                if (document.querySelectorAll('table, [role="grid"]').length > 0 &&
                    document.querySelectorAll('a').length > 10)
                    return 'listing';
                if (document.querySelector(
                    'article, [class*="detail"], [class*="product"], [itemtype*="schema.org"]'
                ))
                    return 'detail';
                return 'static';
            }""")
        except Exception:
            return "static"
