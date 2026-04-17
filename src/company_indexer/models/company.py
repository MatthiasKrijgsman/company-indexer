import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from company_indexer.db import Base


class NameType(str, enum.Enum):
    """How a company is referred to. Mirrors the distinctions KVK makes.

    - statutory: the legal entity name (statutaire naam)
    - trade: a registered trade name / DBA (handelsnaam)
    - short: a short form of the legal name (verkorte naam)
    - alias: anything else we discover (e.g. a brand name from a website)
    """

    STATUTORY = "statutory"
    TRADE = "trade"
    SHORT = "short"
    ALIAS = "alias"


# Shared Enum type so the Postgres enum is named consistently.
name_type_enum = Enum(
    NameType,
    name="name_type",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    kvk_number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    names: Mapped[list["CompanyName"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="CompanyName.id",
    )
    addresses: Mapped[list["Address"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="Address.id",
    )


class CompanyName(Base):
    __tablename__ = "company_names"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[NameType] = mapped_column(name_type_enum)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="names")


# Only one statutory name per company — other types may repeat freely.
Index(
    "ix_company_names_unique_statutory",
    CompanyName.company_id,
    unique=True,
    postgresql_where=CompanyName.type == NameType.STATUTORY,
)
# Case-insensitive search support for GET /companies?q=...
Index(
    "ix_company_names_name_lower",
    func.lower(CompanyName.name),
)


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    house_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="NL")
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    geocoded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="addresses")
