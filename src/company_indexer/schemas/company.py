from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from company_indexer.models import NameType


class CompanyNameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    type: NameType


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    street: str | None
    house_number: str | None
    postcode: str | None
    city: str | None
    country: str
    lat: Decimal | None
    lon: Decimal | None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kvk_number: str
    names: list[CompanyNameRead]
    addresses: list[AddressRead]


class CompanyListResponse(BaseModel):
    items: list[CompanyRead]
    limit: int
    offset: int
