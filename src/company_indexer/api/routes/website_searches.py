from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from company_indexer.api.deps import get_session
from company_indexer.config import get_settings
from company_indexer.models import Company, WebsiteSearch, WebsiteSearchStatus
from company_indexer.schemas.website_search import WebsiteSearchDetail, WebsiteSearchRead
from company_indexer.serper.client import search as serper_search
from company_indexer.serper.excluded_domains import build_query

router = APIRouter(prefix="/companies", tags=["website-search"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/{kvk_number}/website-search",
    response_model=WebsiteSearchRead,
)
async def trigger_website_search(
    kvk_number: str, session: SessionDep
) -> WebsiteSearchRead:
    company = (
        await session.scalars(select(Company).where(Company.kvk_number == kvk_number))
    ).one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with KVK number {kvk_number!r} not found",
        )

    query = build_query(f'kvk "{kvk_number}"')
    result = await serper_search(query, get_settings().serper_api_key)

    record = WebsiteSearch(
        company_id=company.id,
        query=query,
        status=WebsiteSearchStatus.SUCCESS if result.ok else WebsiteSearchStatus.FAILED,
        error=result.error,
        results=result.results,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Serper search failed: {result.error}",
        )
    return WebsiteSearchRead.model_validate(record)


@router.get(
    "/{kvk_number}/website-search",
    response_model=list[WebsiteSearchDetail],
)
async def list_website_searches(
    kvk_number: str, session: SessionDep
) -> list[WebsiteSearchDetail]:
    company = (
        await session.scalars(select(Company).where(Company.kvk_number == kvk_number))
    ).one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with KVK number {kvk_number!r} not found",
        )

    stmt = (
        select(WebsiteSearch)
        .where(WebsiteSearch.company_id == company.id)
        .order_by(WebsiteSearch.created_at.desc(), WebsiteSearch.id.desc())
    )
    rows = (await session.scalars(stmt)).all()
    return [WebsiteSearchDetail.model_validate(r) for r in rows]
