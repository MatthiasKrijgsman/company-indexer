"""Per-company scrape loop.

Called inline from the HTTP route. Creates one ``WebsiteScrape`` row and a
single child ``WebsitePage`` row for the homepage. Raw HTML is saved to disk
via ``storage``; the on-disk path is stored in ``WebsitePage.html_path``.
"""

import asyncio
import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from company_indexer.models import (
    Company,
    CompanyWebsite,
    WebsitePage,
    WebsitePageFetchMethod,
    WebsitePageStatus,
    WebsiteScrape,
    WebsiteScrapeStatus,
)
from company_indexer.scraper import storage
from company_indexer.scraper.detect import detect
from company_indexer.scraper.discover import normalize_url
from company_indexer.scraper.extract import extract
from company_indexer.scraper.fetch import FetchResult, build_client, fetch
from company_indexer.scraper.headers import pick_profile


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _page_status_from_fetch(result: FetchResult) -> WebsitePageStatus:
    """Map a pure-transport FetchResult error code to a WebsitePageStatus."""
    match result.error:
        case "timeout":
            return WebsitePageStatus.TIMEOUT
        case "dead_domain":
            return WebsitePageStatus.DEAD_DOMAIN
        case "network_error":
            return WebsitePageStatus.NETWORK_ERROR
        case "http_4xx":
            return WebsitePageStatus.HTTP_4XX
        case "http_5xx":
            return WebsitePageStatus.HTTP_5XX
        case "non_html":
            return WebsitePageStatus.NON_HTML
        case _:
            return WebsitePageStatus.NETWORK_ERROR


def _classify(result: FetchResult) -> WebsitePageStatus:
    """Combine fetch outcome + JS/block detection into a final page status."""
    if result.html is None:
        return _page_status_from_fetch(result)
    verdict = detect(result)
    if verdict.verdict == "blocked":
        return WebsitePageStatus.BLOCKED
    if verdict.verdict == "js_required":
        return WebsitePageStatus.JS_REQUIRED
    if not result.ok:
        return _page_status_from_fetch(result)
    return WebsitePageStatus.OK


async def _persist_page(
    session: AsyncSession,
    scrape: WebsiteScrape,
    company_id: int,
    url: str,
    result: FetchResult,
) -> WebsitePage:
    """Classify, extract, persist HTML to disk, insert the WebsitePage row."""
    status = _classify(result)
    page = WebsitePage(
        scrape_id=scrape.id,
        url=url,
        normalized_url=normalize_url(result.final_url or url),
        fetch_method=WebsitePageFetchMethod.HTTP,
        status=status,
        http_status=result.status,
        content_type=result.content_type,
        fetched_at=_now(),
    )

    if status == WebsitePageStatus.OK and result.html is not None:
        extracted = await asyncio.to_thread(extract, result.html, url)
        page.markdown = extracted.markdown
        page.title = extracted.title
        if extracted.markdown:
            page.content_hash = _hash(extracted.markdown)

    session.add(page)
    await session.flush()

    if result.html is not None:
        try:
            page.html_path = await storage.save_html(
                company_id, scrape.id, page.id, result.html
            )
        except OSError:
            page.html_path = None

    return page


def _scrape_outcome(status: WebsitePageStatus) -> tuple[WebsiteScrapeStatus, str | None]:
    """Map the homepage page status to the whole-scrape status + error code."""
    if status == WebsitePageStatus.OK:
        return WebsiteScrapeStatus.OK, None
    if status == WebsitePageStatus.DEAD_DOMAIN:
        return WebsiteScrapeStatus.SKIPPED_DEAD_DOMAIN, "dead_domain"
    if status == WebsitePageStatus.JS_REQUIRED:
        return WebsiteScrapeStatus.SKIPPED_JS_HEAVY, "js_required"
    return WebsiteScrapeStatus.FAILED, status.value


async def scrape_company(
    session: AsyncSession, company: Company, website: CompanyWebsite
) -> WebsiteScrape:
    """Scrape one company. Always returns a persisted ``WebsiteScrape``.

    Slice 1b: homepage-only. Starts from ``website.homepage_url`` (scheme +
    host + ``/``) and fetches exactly that one URL — no subpage discovery.
    """
    assert website.homepage_url is not None
    profile = pick_profile(company.id)

    scrape = WebsiteScrape(
        company_id=company.id,
        source_website_id=website.id,
        status=WebsiteScrapeStatus.OK,
        started_at=_now(),
    )
    session.add(scrape)
    await session.flush()

    async with build_client(profile) as client:
        homepage_result = await fetch(client, website.homepage_url)
        homepage_page = await _persist_page(
            session, scrape, company.id, website.homepage_url, homepage_result
        )

    scrape.status, scrape.error = _scrape_outcome(homepage_page.status)
    scrape.pages_attempted = 1
    scrape.pages_ok = 1 if homepage_page.status == WebsitePageStatus.OK else 0
    scrape.pages_failed = 1 - scrape.pages_ok
    scrape.finished_at = _now()
    await session.commit()
    return scrape
