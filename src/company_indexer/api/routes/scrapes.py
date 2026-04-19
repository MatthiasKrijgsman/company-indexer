from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company_indexer.api.deps import get_session
from company_indexer.models import (
    Company,
    CompanyWebsite,
    WebsiteScrape,
)
from company_indexer.schemas.website_scrape import WebsiteScrapeRead
from company_indexer.scraper.orchestrator import scrape_company

router = APIRouter(prefix="/companies", tags=["scrape"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _load_company(session: AsyncSession, kvk_number: str) -> Company:
    stmt = select(Company).where(Company.kvk_number == kvk_number)
    company = (await session.scalars(stmt)).one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with KVK number {kvk_number!r} not found",
        )
    return company


async def _load_latest_resolved_website(
    session: AsyncSession, company_id: int
) -> CompanyWebsite | None:
    stmt = (
        select(CompanyWebsite)
        .where(
            CompanyWebsite.company_id == company_id,
            CompanyWebsite.homepage_url.is_not(None),
        )
        .order_by(CompanyWebsite.created_at.desc(), CompanyWebsite.id.desc())
        .limit(1)
    )
    return (await session.scalars(stmt)).one_or_none()


@router.post(
    "/{kvk_number}/scrape",
    response_model=WebsiteScrapeRead,
)
async def trigger_scrape(kvk_number: str, session: SessionDep) -> WebsiteScrapeRead:
    company = await _load_company(session, kvk_number)
    website = await _load_latest_resolved_website(session, company.id)
    if website is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No resolved website on record for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/resolve-website first."
            ),
        )

    scrape = await scrape_company(session, company, website)
    return await _hydrate(session, scrape.id)


@router.get(
    "/{kvk_number}/scrape",
    response_model=WebsiteScrapeRead,
)
async def get_latest_scrape(kvk_number: str, session: SessionDep) -> WebsiteScrapeRead:
    company = await _load_company(session, kvk_number)
    stmt = (
        select(WebsiteScrape)
        .where(WebsiteScrape.company_id == company.id)
        .options(selectinload(WebsiteScrape.pages))
        .order_by(WebsiteScrape.created_at.desc(), WebsiteScrape.id.desc())
        .limit(1)
    )
    scrape = (await session.scalars(stmt)).one_or_none()
    if scrape is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No scrape found for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/scrape first."
            ),
        )
    return WebsiteScrapeRead.model_validate(scrape)


@router.get(
    "/{kvk_number}/scrapes",
    response_model=list[WebsiteScrapeRead],
)
async def list_scrapes(
    kvk_number: str, session: SessionDep
) -> list[WebsiteScrapeRead]:
    company = await _load_company(session, kvk_number)
    stmt = (
        select(WebsiteScrape)
        .where(WebsiteScrape.company_id == company.id)
        .options(selectinload(WebsiteScrape.pages))
        .order_by(WebsiteScrape.created_at.desc(), WebsiteScrape.id.desc())
    )
    rows = (await session.scalars(stmt)).all()
    return [WebsiteScrapeRead.model_validate(r) for r in rows]


async def _hydrate(session: AsyncSession, scrape_id: int) -> WebsiteScrapeRead:
    stmt = (
        select(WebsiteScrape)
        .where(WebsiteScrape.id == scrape_id)
        .options(selectinload(WebsiteScrape.pages))
    )
    scrape = (await session.scalars(stmt)).one()
    return WebsiteScrapeRead.model_validate(scrape)
