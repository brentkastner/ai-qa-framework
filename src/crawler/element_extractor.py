"""DOM element extraction — catalogs interactive elements on a page."""

from __future__ import annotations

import hashlib
import logging

from playwright.async_api import Page

from src.models.site_model import ElementModel

logger = logging.getLogger(__name__)


async def extract_elements(page: Page) -> list[ElementModel]:
    """Extract all interactive and notable elements from a page."""
    try:
        raw_elements = await page.evaluate("""() => {
            const interactiveTags = new Set([
                'a', 'button', 'input', 'select', 'textarea', 'details', 'summary'
            ]);
            const interactiveRoles = new Set([
                'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox',
                'listbox', 'menuitem', 'tab', 'switch', 'slider'
            ]);

            function getSelector(el) {
                // Prefer data-testid
                if (el.dataset && el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
                // Then id
                if (el.id) return `#${CSS.escape(el.id)}`;
                // Then name attribute for form elements
                if (el.name && ['input', 'select', 'textarea'].includes(el.tagName.toLowerCase())) {
                    return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                }
                // Then aria-label
                if (el.getAttribute('aria-label')) {
                    return `[aria-label="${el.getAttribute('aria-label')}"]`;
                }
                // Fallback: tag + class + nth
                let sel = el.tagName.toLowerCase();
                if (el.className && typeof el.className === 'string') {
                    const cls = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
                    if (cls) sel += '.' + cls;
                }
                return sel;
            }

            function getRole(el) {
                if (el.getAttribute('role')) return el.getAttribute('role');
                const tag = el.tagName.toLowerCase();
                if (tag === 'a') return 'link';
                if (tag === 'button') return 'button';
                if (tag === 'input') {
                    const t = el.type || 'text';
                    if (t === 'checkbox') return 'checkbox';
                    if (t === 'radio') return 'radio';
                    if (t === 'submit') return 'button';
                    return 'textbox';
                }
                if (tag === 'select') return 'combobox';
                if (tag === 'textarea') return 'textbox';
                return '';
            }

            function getElementType(el) {
                const tag = el.tagName.toLowerCase();
                if (tag === 'a') return 'link';
                if (tag === 'button' || (tag === 'input' && el.type === 'submit')) return 'button';
                if (tag === 'input') return 'input';
                if (tag === 'select') return 'dropdown';
                if (tag === 'textarea') return 'textarea';
                if (el.getAttribute('role') === 'tab') return 'tab';
                if (el.getAttribute('role') === 'menuitem') return 'menuitem';
                return tag;
            }

            const results = [];
            const allElements = document.querySelectorAll('*');
            for (const el of allElements) {
                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || '';
                const isClickable = el.onclick || el.getAttribute('onclick');
                const isInteractive = interactiveTags.has(tag) ||
                    interactiveRoles.has(role) ||
                    isClickable ||
                    el.getAttribute('tabindex') === '0';

                if (!isInteractive) continue;
                // Skip hidden elements
                if (el.offsetParent === null && !el.closest('details')) continue;

                const attrs = {};
                for (const attr of el.attributes) {
                    if (['class', 'style'].includes(attr.name)) continue;
                    attrs[attr.name] = attr.value;
                }

                results.push({
                    tag: tag,
                    selector: getSelector(el),
                    role: getRole(el),
                    text_content: (el.textContent || '').trim().substring(0, 100),
                    is_interactive: true,
                    element_type: getElementType(el),
                    attributes: attrs,
                });
            }
            return results;
        }""")

        elements = []
        for i, raw in enumerate(raw_elements):
            eid = hashlib.md5(f"{raw['selector']}:{i}".encode()).hexdigest()[:10]
            elements.append(
                ElementModel(
                    element_id=eid,
                    tag=raw.get("tag", ""),
                    selector=raw.get("selector", ""),
                    role=raw.get("role", ""),
                    text_content=raw.get("text_content", ""),
                    is_interactive=raw.get("is_interactive", True),
                    element_type=raw.get("element_type", ""),
                    attributes=raw.get("attributes", {}),
                )
            )
        logger.debug("Extracted %d interactive elements", len(elements))
        return elements

    except Exception as e:
        logger.error("Element extraction failed: %s", e)
        return []
