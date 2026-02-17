"""Shared URL utilities — normalize URLs and derive stable page IDs."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    query = ""
    if parsed.query:
        params = sorted(parsed.query.split("&"))
        query = "?" + "&".join(params)
    return f"{parsed.scheme}://{parsed.netloc}{path}{query}"


def page_id_from_url(url: str) -> str:
    """Generate a stable page ID from the normalized URL."""
    return hashlib.md5(normalize_url(url).encode()).hexdigest()[:12]
