from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company_indexer.api.deps import get_session
from company_indexer.models import Address, Company
from company_indexer.pdok.client import geocode
from company_indexer.schemas.company import CompanyRead

router = APIRouter(prefix="/companies", tags=["geocoding"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _build_query(address: Address) -> str | None:
    parts: list[str] = []
    if address.street:
        parts.append(address.street)
    if address.house_number:
        parts.append(address.house_number)
    if address.postcode:
        parts.append(address.postcode)
    if address.city:
        parts.append(address.city)
    return " ".join(parts) if parts else None


@router.post(
    "/{kvk_number}/geocode",
    response_model=CompanyRead,
)
async def geocode_company(kvk_number: str, session: SessionDep) -> CompanyRead:
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

    network_errors: list[str] = []
    for address in company.addresses:
        query = _build_query(address)
        if query is None:
            continue

        result = await geocode(query)
        address.geocoded_at = datetime.now(UTC)
        if result.ok:
            address.lat = result.lat
            address.lon = result.lon
        elif result.error and result.error != "no_match":
            # no_match is a normal outcome; leave lat/lon as-is and move on.
            # Other errors are infrastructure-level — surface via 502 below.
            network_errors.append(result.error)

    await session.commit()

    if network_errors:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"PDOK errors on one or more addresses: {network_errors}",
        )
    return CompanyRead.model_validate(company)
