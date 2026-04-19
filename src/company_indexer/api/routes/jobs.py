from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company_indexer.api.deps import get_session
from company_indexer.jobs.orchestrator import resolve_careers_url, scrape_jobs
from company_indexer.models import (
    Company,
    CompanyCareersUrl,
    JobsScrape,
    WebsiteScrape,
    WebsiteScrapeStatus,
)
from company_indexer.schemas.jobs import CompanyCareersUrlRead, JobsScrapeRead

router = APIRouter(prefix="/companies", tags=["jobs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _load_company(session: AsyncSession, kvk_number: str) -> Company:
    stmt = (
        select(Company)
        .where(Company.kvk_number == kvk_number)
        .options(selectinload(Company.names), selectinload(Company.addresses))
    )
    company = (await session.scalars(stmt)).one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with KVK number {kvk_number!r} not found",
        )
    return company


async def _load_latest_ok_scrape(
    session: AsyncSession, company_id: int
) -> WebsiteScrape | None:
    stmt = (
        select(WebsiteScrape)
        .where(
            WebsiteScrape.company_id == company_id,
            WebsiteScrape.status == WebsiteScrapeStatus.OK,
        )
        .options(
            selectinload(WebsiteScrape.pages),
            selectinload(WebsiteScrape.source_website),
        )
        .order_by(WebsiteScrape.created_at.desc(), WebsiteScrape.id.desc())
        .limit(1)
    )
    return (await session.scalars(stmt)).one_or_none()


async def _load_latest_careers(
    session: AsyncSession, company_id: int
) -> CompanyCareersUrl | None:
    stmt = (
        select(CompanyCareersUrl)
        .where(CompanyCareersUrl.company_id == company_id)
        .order_by(CompanyCareersUrl.created_at.desc(), CompanyCareersUrl.id.desc())
        .limit(1)
    )
    return (await session.scalars(stmt)).one_or_none()


@router.post(
    "/{kvk_number}/resolve-careers",
    response_model=CompanyCareersUrlRead,
)
async def resolve_careers_endpoint(
    kvk_number: str, session: SessionDep
) -> CompanyCareersUrlRead:
    company = await _load_company(session, kvk_number)
    scrape = await _load_latest_ok_scrape(session, company.id)
    if scrape is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No OK website scrape on record for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/scrape first."
            ),
        )

    record = await resolve_careers_url(session, company, scrape)

    if record.reason.startswith("resolver_error:"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Careers resolution failed: {record.reason}",
        )
    return CompanyCareersUrlRead.model_validate(record)


@router.get(
    "/{kvk_number}/careers-url",
    response_model=CompanyCareersUrlRead,
)
async def get_careers_url(
    kvk_number: str, session: SessionDep
) -> CompanyCareersUrlRead:
    company = await _load_company(session, kvk_number)
    row = await _load_latest_careers(session, company.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No careers-URL resolution for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/resolve-careers first."
            ),
        )
    return CompanyCareersUrlRead.model_validate(row)


@router.post(
    "/{kvk_number}/scrape-jobs",
    response_model=JobsScrapeRead,
)
async def scrape_jobs_endpoint(
    kvk_number: str, session: SessionDep
) -> JobsScrapeRead:
    company = await _load_company(session, kvk_number)
    careers = await _load_latest_careers(session, company.id)
    if careers is None or careers.url is None:
        detail = (
            f"No careers URL on record for {kvk_number!r}. "
            if careers is None
            else f"Latest careers resolution for {kvk_number!r} is null "
            f"({careers.reason!r}); nothing to scrape. "
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail + f"Call POST /companies/{kvk_number}/resolve-careers first.",
        )

    scrape = await _load_latest_ok_scrape(session, company.id)
    if scrape is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No OK website scrape on record for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/scrape first."
            ),
        )

    jobs_scrape = await scrape_jobs(session, company, careers, scrape)
    return await _hydrate(session, jobs_scrape.id)


@router.get(
    "/{kvk_number}/jobs",
    response_model=JobsScrapeRead,
)
async def get_latest_jobs_scrape(
    kvk_number: str, session: SessionDep
) -> JobsScrapeRead:
    company = await _load_company(session, kvk_number)
    stmt = (
        select(JobsScrape)
        .where(JobsScrape.company_id == company.id)
        .options(selectinload(JobsScrape.jobs))
        .order_by(JobsScrape.created_at.desc(), JobsScrape.id.desc())
        .limit(1)
    )
    row = (await session.scalars(stmt)).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No jobs scrape found for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/scrape-jobs first."
            ),
        )
    return JobsScrapeRead.model_validate(row)


@router.get(
    "/{kvk_number}/jobs-history",
    response_model=list[JobsScrapeRead],
)
async def list_jobs_scrapes(
    kvk_number: str, session: SessionDep
) -> list[JobsScrapeRead]:
    company = await _load_company(session, kvk_number)
    stmt = (
        select(JobsScrape)
        .where(JobsScrape.company_id == company.id)
        .options(selectinload(JobsScrape.jobs))
        .order_by(JobsScrape.created_at.desc(), JobsScrape.id.desc())
    )
    rows = (await session.scalars(stmt)).all()
    return [JobsScrapeRead.model_validate(r) for r in rows]


async def _hydrate(session: AsyncSession, jobs_scrape_id: int) -> JobsScrapeRead:
    stmt = (
        select(JobsScrape)
        .where(JobsScrape.id == jobs_scrape_id)
        .options(selectinload(JobsScrape.jobs))
    )
    row = (await session.scalars(stmt)).one()
    return JobsScrapeRead.model_validate(row)
