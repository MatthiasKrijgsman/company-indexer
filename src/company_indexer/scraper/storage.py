"""Filesystem writer for raw HTML.

Layout under the configured root:
    {company_id}/{scrape_id}/{page_id}.html

The returned path is relative to the root so the root can move without a
data migration. Writes go through ``asyncio.to_thread`` because the filesystem
API is blocking.
"""

import asyncio
from pathlib import Path

from company_indexer.config import get_settings


def _root() -> Path:
    return Path(get_settings().scraped_html_dir)


def _relative_path(company_id: int, scrape_id: int, page_id: int) -> Path:
    return Path(str(company_id), str(scrape_id), f"{page_id}.html")


def _write_sync(absolute: Path, html: str) -> None:
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_text(html, encoding="utf-8")


async def save_html(
    company_id: int, scrape_id: int, page_id: int, html: str
) -> str:
    """Persist ``html`` to disk and return the root-relative path string."""
    rel = _relative_path(company_id, scrape_id, page_id)
    absolute = _root() / rel
    await asyncio.to_thread(_write_sync, absolute, html)
    return str(rel)
