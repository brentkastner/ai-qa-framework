"""SPA-specific routing detection and handling."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def detect_spa_type(page: Page) -> str:
    """Detect if the page is a SPA and what type of routing it uses."""
    try:
        spa_info = await page.evaluate("""() => {
            // Check for common SPA frameworks
            const hasReact = !!document.querySelector('[data-reactroot], [data-reactid], #root, #__next');
            const hasVue = !!document.querySelector('[data-v-], #app, [data-server-rendered]');
            const hasAngular = !!document.querySelector('[ng-app], [data-ng-app], app-root');

            // Check routing type
            const hasHashRouting = window.location.hash.length > 1;
            const hasHistoryAPI = typeof window.history.pushState === 'function';

            let routingType = 'traditional';
            if (hasHashRouting) routingType = 'hash';
            else if (hasReact || hasVue || hasAngular) routingType = 'history';

            return {
                is_spa: hasReact || hasVue || hasAngular,
                framework: hasReact ? 'react' : hasVue ? 'vue' : hasAngular ? 'angular' : 'unknown',
                routing_type: routingType,
            };
        }""")
        logger.debug("SPA detection: %s", spa_info)
        return spa_info.get("routing_type", "traditional")
    except Exception:
        return "traditional"


async def discover_spa_routes(page: Page, base_url: str) -> list[str]:
    """Attempt to discover SPA routes by monitoring URL changes during interaction."""
    discovered = set()

    try:
        # Look for router links (React Router, Vue Router, etc.)
        routes = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href]');
            const routes = [];
            for (const link of links) {
                const href = link.getAttribute('href');
                if (href && (href.startsWith('/') || href.startsWith('#/'))) {
                    routes.push(href);
                }
            }
            return [...new Set(routes)];
        }""")

        parsed_base = urlparse(base_url)
        for route in routes:
            if route.startswith("#/"):
                full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{route}"
            elif route.startswith("/"):
                full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{route}"
            else:
                continue
            discovered.add(full_url)

    except Exception as e:
        logger.debug("SPA route discovery error: %s", e)

    return list(discovered)
