"""Manual seed for local development.

Run with: python -m company_indexer.scripts.seed_companies

Idempotent: companies are keyed on kvk_number and skipped if already present,
so you can re-run freely after restarting containers.
"""

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select

from company_indexer.db import create_all, get_sessionmaker
from company_indexer.models import Address, Company, CompanyName, NameType


@dataclass
class NameSeed:
    name: str
    type: NameType


@dataclass
class AddressSeed:
    street: str | None = None
    house_number: str | None = None
    postcode: str | None = None
    city: str | None = None
    country: str = "NL"


@dataclass
class CompanySeed:
    kvk_number: str
    names: list[NameSeed]
    addresses: list[AddressSeed] = field(default_factory=list)


SEED_COMPANIES: list[CompanySeed] = [
    CompanySeed(
        kvk_number="17001910",
        names=[
            NameSeed("Koninklijke Philips N.V.", NameType.STATUTORY),
            NameSeed("Philips", NameType.TRADE),
        ],
        addresses=[
            AddressSeed(
                street="Amstelplein",
                house_number="2",
                postcode="1096BC",
                city="Amsterdam",
            ),
        ],
    ),
    CompanySeed(
        kvk_number="34088856",
        names=[
            NameSeed("Bol.com B.V.", NameType.STATUTORY),
            NameSeed("Bol", NameType.TRADE),
            NameSeed("bol.com", NameType.ALIAS),
        ],
        addresses=[
            AddressSeed(
                street="Papendorpseweg",
                house_number="100",
                postcode="3528BJ",
                city="Utrecht",
            ),
        ],
    ),
    CompanySeed(
        kvk_number="24180869",
        names=[
            NameSeed("Coolblue B.V.", NameType.STATUTORY),
            NameSeed("Coolblue", NameType.TRADE),
        ],
        addresses=[
            AddressSeed(
                street="Weena",
                house_number="664",
                postcode="3012CN",
                city="Rotterdam",
            ),
        ],
    ),
]


async def seed() -> None:
    await create_all()

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing_kvks = set(
            (
                await session.scalars(
                    select(Company.kvk_number).where(
                        Company.kvk_number.in_([c.kvk_number for c in SEED_COMPANIES])
                    )
                )
            ).all()
        )

        created = 0
        for seed_company in SEED_COMPANIES:
            if seed_company.kvk_number in existing_kvks:
                continue

            company = Company(
                kvk_number=seed_company.kvk_number,
                names=[
                    CompanyName(name=n.name, type=n.type) for n in seed_company.names
                ],
                addresses=[
                    Address(
                        street=a.street,
                        house_number=a.house_number,
                        postcode=a.postcode,
                        city=a.city,
                        country=a.country,
                    )
                    for a in seed_company.addresses
                ],
            )
            session.add(company)
            created += 1

        await session.commit()

    print(f"Seed complete. Inserted {created} new companies, skipped {len(SEED_COMPANIES) - created}.")


if __name__ == "__main__":
    asyncio.run(seed())
