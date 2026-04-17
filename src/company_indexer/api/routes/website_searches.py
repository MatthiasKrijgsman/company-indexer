from typing import Annotated

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company_indexer.api.deps import get_session
from company_indexer.config import get_settings
from company_indexer.llm.website_resolver import (
    CompanyContext,
    MODEL as RESOLVER_MODEL,
    extract_candidates,
    resolve,
)
from company_indexer.models import (
    Company,
    CompanyWebsite,
    WebsiteConfidence,
    WebsiteSearch,
    WebsiteSearchStatus,
)
from company_indexer.schemas.company_website import WebsiteRead
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


@router.post(
    "/{kvk_number}/resolve-website",
    response_model=WebsiteRead,
)
async def resolve_website_endpoint(
    kvk_number: str, session: SessionDep
) -> WebsiteRead:
    company_stmt = (
        select(Company)
        .where(Company.kvk_number == kvk_number)
        .options(selectinload(Company.names), selectinload(Company.addresses))
    )
    company = (await session.scalars(company_stmt)).one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with KVK number {kvk_number!r} not found",
        )

    search_stmt = (
        select(WebsiteSearch)
        .where(
            WebsiteSearch.company_id == company.id,
            WebsiteSearch.status == WebsiteSearchStatus.SUCCESS,
        )
        .order_by(WebsiteSearch.created_at.desc(), WebsiteSearch.id.desc())
        .limit(1)
    )
    latest_search = (await session.scalars(search_stmt)).one_or_none()
    if latest_search is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No successful website search found for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/website-search first."
            ),
        )

    candidates = extract_candidates(latest_search.results)
    ctx = CompanyContext(
        kvk_number=kvk_number,
        names=[(n.name, n.type.value) for n in company.names],
        city=company.addresses[0].city if company.addresses else None,
    )

    llm_model = ""
    llm_error: str | None = None

    if not candidates:
        url: str | None = None
        confidence = WebsiteConfidence.NONE
        reason = "no search candidates"
    else:
        try:
            resolution = await resolve(ctx, candidates)
            llm_model = RESOLVER_MODEL
            url = resolution.website
            reason = resolution.reason
            confidence = (
                WebsiteConfidence.NONE
                if url is None
                else WebsiteConfidence(resolution.confidence)
            )
        except (anthropic.APIError, ValueError) as e:
            # APIError covers network/timeout/auth/overloaded; ValueError catches
            # response validation failures (bad JSON shape, refusal, etc.).
            url = None
            confidence = WebsiteConfidence.NONE
            reason = f"resolver_error: {type(e).__name__}"
            llm_error = reason

    record = CompanyWebsite(
        company_id=company.id,
        source_search_id=latest_search.id,
        url=url,
        confidence=confidence,
        reason=reason,
        llm_model=llm_model,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    if llm_error is not None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Website resolution failed: {llm_error}",
        )
    return WebsiteRead.model_validate(record)


@router.get(
    "/{kvk_number}/website",
    response_model=WebsiteRead,
)
async def get_website(kvk_number: str, session: SessionDep) -> WebsiteRead:
    company = (
        await session.scalars(select(Company).where(Company.kvk_number == kvk_number))
    ).one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with KVK number {kvk_number!r} not found",
        )

    stmt = (
        select(CompanyWebsite)
        .where(CompanyWebsite.company_id == company.id)
        .order_by(CompanyWebsite.created_at.desc(), CompanyWebsite.id.desc())
        .limit(1)
    )
    row = (await session.scalars(stmt)).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No website resolution found for {kvk_number!r}. "
                f"Call POST /companies/{kvk_number}/resolve-website first."
            ),
        )
    return WebsiteRead.model_validate(row)
