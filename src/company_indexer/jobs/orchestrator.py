"""Per-company jobs pipeline: resolve careers URL, then extract jobs.

Both entrypoints are called inline from the HTTP routes. Each persists
its own rows before returning — errors are recorded, not raised.
"""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from company_indexer.jobs import extractor, resolver
from company_indexer.jobs.candidates import Candidate, build_candidates
from company_indexer.models import (
    Company,
    CompanyCareersUrl,
    Job,
    JobEmploymentType,
    JobsScrape,
    JobsScrapeStatus,
    WebsiteConfidence,
    WebsitePage,
    WebsitePageStatus,
    WebsiteScrape,
)
from company_indexer.scraper import storage
from company_indexer.scraper.detect import detect
from company_indexer.scraper.extract import extract
from company_indexer.scraper.fetch import FetchResult, build_client, fetch
from company_indexer.scraper.headers import pick_profile


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_company_context(
    company: Company, scrape: WebsiteScrape
) -> resolver.CompanyContext:
    homepage_url = scrape.source_website.homepage_url or ""
    city = company.addresses[0].city if company.addresses else None
    return resolver.CompanyContext(
        kvk_number=company.kvk_number,
        names=[(n.name, n.type.value) for n in company.names],
        city=city,
        homepage_url=homepage_url,
    )


async def _read_homepage_html(scrape: WebsiteScrape) -> tuple[str, str] | None:
    """Return (homepage_url, html) for the homepage WebsitePage, or None."""
    homepage_page = _homepage_page(scrape)
    if homepage_page is None or homepage_page.html_path is None:
        return None
    path = Path(storage._root()) / homepage_page.html_path
    try:
        html = await asyncio.to_thread(path.read_text, encoding="utf-8")
    except OSError:
        return None
    return homepage_page.url, html


def _homepage_page(scrape: WebsiteScrape) -> WebsitePage | None:
    """Slice-1 scrapes have exactly one page — the homepage. Defensive anyway."""
    for page in scrape.pages:
        if page.status == WebsitePageStatus.OK:
            return page
    return None


async def resolve_careers_url(
    session: AsyncSession, company: Company, scrape: WebsiteScrape
) -> CompanyCareersUrl:
    """Stage A: pick the company's careers URL from its homepage links.

    Always returns a persisted ``CompanyCareersUrl`` row — null url is a
    valid outcome.
    """
    ctx = _build_company_context(company, scrape)
    homepage = await _read_homepage_html(scrape)
    candidates: list[Candidate] = (
        build_candidates(homepage[1], homepage[0]) if homepage else []
    )

    url: str | None = None
    confidence = WebsiteConfidence.NONE
    reason = ""
    llm_model = ""

    if not candidates:
        reason = "no_candidates"
    else:
        try:
            pick = await resolver.pick_careers_url(ctx, candidates)
            llm_model = resolver.MODEL
            url = pick.chosen_url
            reason = pick.reason
            confidence = (
                WebsiteConfidence.NONE
                if url is None
                else WebsiteConfidence(pick.confidence)
            )
        except (anthropic.APIError, ValueError) as e:
            reason = f"resolver_error: {type(e).__name__}"

    record = CompanyCareersUrl(
        company_id=company.id,
        source_scrape_id=scrape.id,
        url=url,
        confidence=confidence,
        reason=reason,
        llm_model=llm_model,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


def _classify_fetch(result: FetchResult) -> JobsScrapeStatus:
    """Map a FetchResult to a JobsScrape status."""
    if result.html is None:
        return JobsScrapeStatus.FAILED
    verdict = detect(result)
    if verdict.verdict == "blocked":
        return JobsScrapeStatus.BLOCKED
    if verdict.verdict == "js_required":
        return JobsScrapeStatus.JS_REQUIRED
    if not result.ok:
        return JobsScrapeStatus.FAILED
    return JobsScrapeStatus.OK


async def scrape_jobs(
    session: AsyncSession,
    company: Company,
    careers: CompanyCareersUrl,
    scrape: WebsiteScrape,
) -> JobsScrape:
    """Stage B: fetch the careers URL, extract jobs, persist rows.

    ``scrape`` is the upstream ``WebsiteScrape`` used only to build
    ``CompanyContext`` for the LLM — we do not reuse its ``WebsitePage``
    rows. The careers URL is fetched fresh into a ``JobsScrape``.
    """
    assert careers.url is not None
    ctx = _build_company_context(company, scrape)

    jobs_scrape = JobsScrape(
        company_id=company.id,
        source_careers_id=careers.id,
        fetched_url=careers.url,
        status=JobsScrapeStatus.FAILED,
        started_at=_now(),
    )
    session.add(jobs_scrape)
    await session.flush()

    profile = pick_profile(company.id)
    async with build_client(profile) as client:
        result = await fetch(client, careers.url)

    jobs_scrape.http_status = result.status
    jobs_scrape.fetched_url = result.final_url or careers.url
    status = _classify_fetch(result)
    jobs_scrape.status = status

    if result.html is not None:
        try:
            jobs_scrape.html_path = await storage.save_jobs_html(
                company.id, jobs_scrape.id, result.html
            )
        except OSError:
            jobs_scrape.html_path = None

    if status != JobsScrapeStatus.OK:
        if not result.ok and result.error:
            jobs_scrape.error = result.error
        jobs_scrape.finished_at = _now()
        await session.commit()
        return jobs_scrape

    assert result.html is not None
    extracted = await asyncio.to_thread(extract, result.html, careers.url)
    if extracted.markdown:
        jobs_scrape.content_hash = _hash(extracted.markdown)

    if not extracted.markdown:
        jobs_scrape.status = JobsScrapeStatus.NO_JOBS
        jobs_scrape.finished_at = _now()
        await session.commit()
        return jobs_scrape

    try:
        items = await extractor.extract_jobs(
            ctx, careers.url, extracted.markdown
        )
        jobs_scrape.llm_model = extractor.MODEL
    except (anthropic.APIError, ValueError) as e:
        jobs_scrape.status = JobsScrapeStatus.LLM_ERROR
        jobs_scrape.error = f"extractor_error: {type(e).__name__}"
        jobs_scrape.finished_at = _now()
        await session.commit()
        return jobs_scrape

    if not items:
        jobs_scrape.status = JobsScrapeStatus.NO_JOBS
    else:
        jobs_scrape.status = JobsScrapeStatus.OK
        for item in items:
            session.add(
                Job(
                    jobs_scrape_id=jobs_scrape.id,
                    title=item.title,
                    url=item.url,
                    location=item.location,
                    employment_type=JobEmploymentType(item.employment_type),
                    department=item.department,
                    raw_snippet=item.raw_snippet,
                )
            )

    jobs_scrape.finished_at = _now()
    await session.commit()
    return jobs_scrape
