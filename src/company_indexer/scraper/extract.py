"""Markdown + title extraction from raw HTML.

Wraps trafilatura. trafilatura is sync and CPU-bound (LXML parsing), so
callers should hand this off to a thread via ``asyncio.to_thread``.
"""

from dataclasses import dataclass

import trafilatura
from bs4 import BeautifulSoup


@dataclass
class ExtractResult:
    markdown: str | None
    title: str | None


def extract(html: str, url: str | None = None) -> ExtractResult:
    markdown = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    title = _extract_title(html)
    return ExtractResult(markdown=markdown, title=title)


def _extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()[:512] or None
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()[:512] or None
    return None
