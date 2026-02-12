"""Form analysis — identifies form fields, types, and validation."""

from __future__ import annotations

import hashlib
import logging

from playwright.async_api import Page

from src.models.site_model import FormField, FormModel

logger = logging.getLogger(__name__)


async def analyze_forms(page: Page) -> list[FormModel]:
    """Analyze all forms on a page and return structured form models."""
    try:
        raw_forms = await page.evaluate("""() => {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map((form, fi) => {
                const fields = [];
                const inputs = form.querySelectorAll('input, select, textarea');

                for (const inp of inputs) {
                    const tag = inp.tagName.toLowerCase();
                    let fieldType = 'text';
                    let options = null;

                    if (tag === 'select') {
                        fieldType = 'select';
                        options = Array.from(inp.options).map(o => o.value).filter(v => v);
                    } else if (tag === 'textarea') {
                        fieldType = 'textarea';
                    } else if (tag === 'input') {
                        fieldType = inp.type || 'text';
                    }

                    // Skip hidden/submit fields
                    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(fieldType)) continue;

                    let selector = '';
                    if (inp.id) selector = `#${CSS.escape(inp.id)}`;
                    else if (inp.name) selector = `${tag}[name="${inp.name}"]`;
                    else selector = `form:nth-of-type(${fi + 1}) ${tag}:nth-of-type(${Array.from(form.querySelectorAll(tag)).indexOf(inp) + 1})`;

                    fields.push({
                        name: inp.name || inp.id || '',
                        field_type: fieldType,
                        required: inp.required || inp.getAttribute('aria-required') === 'true',
                        validation_pattern: inp.pattern || null,
                        options: options,
                        selector: selector,
                    });
                }

                // Find submit button
                let submitSelector = '';
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn) {
                    if (submitBtn.id) submitSelector = `#${CSS.escape(submitBtn.id)}`;
                    else submitSelector = `form:nth-of-type(${fi + 1}) button[type="submit"], form:nth-of-type(${fi + 1}) input[type="submit"]`;
                } else {
                    const anyBtn = form.querySelector('button');
                    if (anyBtn) {
                        if (anyBtn.id) submitSelector = `#${CSS.escape(anyBtn.id)}`;
                        else submitSelector = `form:nth-of-type(${fi + 1}) button`;
                    }
                }

                return {
                    action: form.action || '',
                    method: (form.method || 'GET').toUpperCase(),
                    fields: fields,
                    submit_selector: submitSelector,
                };
            });
        }""")

        forms = []
        for i, raw in enumerate(raw_forms):
            fid = hashlib.md5(f"form:{i}:{raw.get('action', '')}".encode()).hexdigest()[:10]
            fields = [FormField(**f) for f in raw.get("fields", [])]
            forms.append(
                FormModel(
                    form_id=fid,
                    action=raw.get("action", ""),
                    method=raw.get("method", "GET"),
                    fields=fields,
                    submit_selector=raw.get("submit_selector", ""),
                )
            )

        logger.debug("Analyzed %d forms", len(forms))
        return forms

    except Exception as e:
        logger.error("Form analysis failed: %s", e)
        return []
