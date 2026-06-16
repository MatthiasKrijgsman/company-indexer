from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company_indexer.api.deps import get_session
from company_indexer.models import Address, Company, CompanyName, NameType
from company_indexer.schemas.company import (
    CompanyGeoPoint,
    CompanyListResponse,
    CompanyRead,
)

router = APIRouter(prefix="/companies", tags=["companies"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(description="Case-insensitive substring match on any name")] = None,
) -> CompanyListResponse:
    stmt = (
        select(Company)
        .options(selectinload(Company.names), selectinload(Company.addresses))
        .order_by(Company.id)
    )

    if q:
        pattern = f"%{q.lower()}%"
        matching_company_ids = (
            select(CompanyName.company_id)
            .where(func.lower(CompanyName.name).like(pattern))
            .distinct()
        )
        stmt = stmt.where(Company.id.in_(matching_company_ids))

    stmt = stmt.limit(limit).offset(offset)
    companies = (await session.scalars(stmt)).all()

    return CompanyListResponse(
        items=[CompanyRead.model_validate(c) for c in companies],
        limit=limit,
        offset=offset,
    )


def _primary_name(company: Company) -> str:
    """Statutory name if present, else the first name on record."""
    statutory = next(
        (n.name for n in company.names if n.type == NameType.STATUTORY), None
    )
    return statutory or (company.names[0].name if company.names else company.kvk_number)


@router.get("/geo", response_model=list[CompanyGeoPoint])
async def list_geo_points(session: SessionDep) -> list[CompanyGeoPoint]:
    """Every geocoded address as a map point. One point per address that has
    both `lat` and `lon` — a company with two geocoded addresses yields two.
    No pagination: the point set is the whole map."""
    stmt = (
        select(Address)
        .where(Address.lat.is_not(None), Address.lon.is_not(None))
        .options(selectinload(Address.company).selectinload(Company.names))
        .order_by(Address.id)
    )
    addresses = (await session.scalars(stmt)).all()
    return [
        CompanyGeoPoint(
            kvk_number=a.company.kvk_number,
            name=_primary_name(a.company),
            city=a.city,
            lat=a.lat,
            lon=a.lon,
        )
        for a in addresses
    ]


@router.get("/{kvk_number}", response_model=CompanyRead)
async def get_company(kvk_number: str, session: SessionDep) -> CompanyRead:
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
    return CompanyRead.model_validate(company)
