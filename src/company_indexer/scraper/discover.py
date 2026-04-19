"""URL normalization shared by the scraper.

Kept as a separate module so the unique-per-scrape `(scrape_id, normalized_url)`
invariant has one canonical implementation. Subpage discovery was removed in
slice 1b — only the homepage is fetched.
"""

from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """Lowercase host, strip fragment + query, collapse trailing slash."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, netloc, path, "", "", ""))
