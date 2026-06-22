"""Import BV companies from a KVK SQLite dump into the API's Postgres database.

The source (default ``data/companies/companies.sqlite``) is a KVK extract with
``bedrijven`` (companies), ``vestigingen`` (establishments), ``handelsnamen``
(trade names) and ``vestiging_adressen`` (addresses). Only rows with
``rechtsvorm_code = 'BV'`` (Besloten Vennootschap) are imported.

Mapping into our models:

- ``Company.kvk_number``  ← ``bedrijven.kvk_nummer``
- statutory name (``NameType.STATUTORY``) ← ``bedrijven.statutaire_naam``
  (falls back to ``bedrijven.naam``)
- trade names (``NameType.TRADE``) ← ``handelsnamen.handelsnaam`` across the
  company's establishments, de-duplicated (capped at ``MAX_TRADE_NAMES``)
- one primary ``Address`` ← the company's main physical address, picked in
  priority order: Hoofdvestiging ``bezoek`` → Hoofdvestiging ``post`` → any
  ``bezoek`` → any ``post``. (The source has no country, so ``country`` defaults
  to ``NL``; ``lat``/``lon`` stay null for the geocoder to fill later.)

Idempotent and resumable: companies already present (by ``kvk_number``) are
skipped via ``ON CONFLICT DO NOTHING``, and names/addresses are only written for
newly-inserted companies — so re-running after an interruption continues cleanly.

The source is opened read-only; a temporary index on ``vestigingen(kvk_nummer)``
is built in SQLite's temp store (not in the source file) to make the per-batch
joins fast.

Run:

    python -m company_indexer.scripts.import_companies            # full import
    python -m company_indexer.scripts.import_companies --limit 1000   # smoke test
    python -m company_indexer.scripts.import_companies --sqlite /path/to.sqlite
"""

import argparse
import asyncio
import sqlite3
import time

from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from company_indexer.db import create_all, get_engine
from company_indexer.models import Address, Company, CompanyName, NameType

DEFAULT_SQLITE = "data/companies/companies.sqlite"
RECHTSVORM = "BV"
BATCH_SIZE = 2000
MAX_TRADE_NAMES = 20  # cap to avoid pathological holdings with hundreds of names

# Column lengths in the target schema — source values are truncated to fit.
_LEN_KVK = 16
_LEN_NAME = 255
_LEN_STREET = 255
_LEN_HOUSE = 32
_LEN_POSTCODE = 16
_LEN_CITY = 128


def _clip(value: str | None, length: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:length] if value else None


def open_source(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    return con


def build_temp_index(con: sqlite3.Connection) -> None:
    """Copy the establishment → kvk mapping into a temp table indexed by kvk.

    ``vestigingen`` has no index on ``kvk_nummer`` in the source, so gathering a
    company's establishments would full-scan 2.3M rows per batch. The temp table
    lives in SQLite's temp store and leaves the source file untouched.
    """
    cur = con.cursor()
    cur.execute("PRAGMA temp_store = FILE")
    cur.execute(
        "CREATE TEMP TABLE v AS "
        "SELECT vestigingsnummer, kvk_nummer, inschrijvingstype FROM vestigingen"
    )
    cur.execute("CREATE INDEX tv_kvk ON v(kvk_nummer)")
    cur.close()


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def fetch_trade_names(
    con: sqlite3.Connection, kvks: list[str]
) -> dict[str, list[str]]:
    rows = con.execute(
        "SELECT v.kvk_nummer AS k, h.handelsnaam AS n "
        "FROM v JOIN handelsnamen h ON h.vestigingsnummer = v.vestigingsnummer "
        f"WHERE v.kvk_nummer IN ({_placeholders(len(kvks))})",
        kvks,
    )
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["k"], []).append(r["n"])
    return out


def fetch_addresses(
    con: sqlite3.Connection, kvks: list[str]
) -> dict[str, list[sqlite3.Row]]:
    rows = con.execute(
        "SELECT v.kvk_nummer AS k, v.inschrijvingstype AS it, a.adres_type AS at, "
        "a.straat, a.huisnummer, a.postcode, a.plaats "
        "FROM v JOIN vestiging_adressen a ON a.vestigingsnummer = v.vestigingsnummer "
        f"WHERE v.kvk_nummer IN ({_placeholders(len(kvks))})",
        kvks,
    )
    out: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        out.setdefault(r["k"], []).append(r)
    return out


def _address_rank(row: sqlite3.Row) -> tuple[int, int]:
    hoofd = 0 if row["it"] == "Hoofdvestiging" else 1
    bezoek = 0 if row["at"] == "bezoek" else 1
    return (hoofd, bezoek)


def primary_address(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    """Pick the main physical address; None when there's nothing usable."""
    usable = [r for r in rows if r["straat"] or r["plaats"] or r["postcode"]]
    if not usable:
        return None
    return min(usable, key=_address_rank)


def statutory_name(naam: str | None, statutaire_naam: str | None) -> str | None:
    return _clip(statutaire_naam, _LEN_NAME) or _clip(naam, _LEN_NAME)


def build_rows(
    id_by_kvk: dict[str, int],
    info_by_kvk: dict[str, sqlite3.Row],
    trade_by_kvk: dict[str, list[str]],
    addr_by_kvk: dict[str, list[sqlite3.Row]],
) -> tuple[list[dict], list[dict]]:
    """Build CompanyName + Address insert dicts for the newly-inserted companies."""
    name_rows: list[dict] = []
    addr_rows: list[dict] = []

    for kvk, company_id in id_by_kvk.items():
        info = info_by_kvk[kvk]
        seen: set[str] = set()

        statutory = statutory_name(info["naam"], info["statutaire_naam"])
        if statutory:
            name_rows.append(
                {"company_id": company_id, "name": statutory, "type": NameType.STATUTORY}
            )
            seen.add(statutory.lower())

        for raw in trade_by_kvk.get(kvk, []):
            name = _clip(raw, _LEN_NAME)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            name_rows.append(
                {"company_id": company_id, "name": name, "type": NameType.TRADE}
            )
            if len(seen) >= MAX_TRADE_NAMES + 1:  # +1 for the statutory name
                break

        addr = primary_address(addr_by_kvk.get(kvk, []))
        if addr is not None:
            addr_rows.append(
                {
                    "company_id": company_id,
                    "street": _clip(addr["straat"], _LEN_STREET),
                    "house_number": _clip(addr["huisnummer"], _LEN_HOUSE),
                    "postcode": _clip(addr["postcode"], _LEN_POSTCODE),
                    "city": _clip(addr["plaats"], _LEN_CITY),
                    "country": "NL",
                }
            )

    return name_rows, addr_rows


async def import_batch(conn, batch: list[sqlite3.Row], source: sqlite3.Connection) -> int:
    """Insert one batch of companies + their names/addresses. Returns the number
    of newly-inserted companies."""
    kvks = [r["kvk_nummer"] for r in batch]
    info_by_kvk = {r["kvk_nummer"]: r for r in batch}

    insert_companies = (
        pg_insert(Company.__table__)
        .values([{"kvk_number": _clip(k, _LEN_KVK)} for k in kvks])
        .on_conflict_do_nothing(index_elements=["kvk_number"])
        .returning(Company.__table__.c.id, Company.__table__.c.kvk_number)
    )
    result = await conn.execute(insert_companies)
    id_by_kvk = {row.kvk_number: row.id for row in result}
    if not id_by_kvk:
        return 0  # whole batch already imported

    new_kvks = list(id_by_kvk)
    trade_by_kvk = fetch_trade_names(source, new_kvks)
    addr_by_kvk = fetch_addresses(source, new_kvks)
    name_rows, addr_rows = build_rows(id_by_kvk, info_by_kvk, trade_by_kvk, addr_by_kvk)

    if name_rows:
        await conn.execute(insert(CompanyName.__table__), name_rows)
    if addr_rows:
        await conn.execute(insert(Address.__table__), addr_rows)

    return len(id_by_kvk)


async def run(sqlite_path: str, batch_size: int, limit: int | None) -> None:
    await create_all()
    engine = get_engine()

    source = open_source(sqlite_path)
    print(f"Source: {sqlite_path}")
    total_bv = source.execute(
        "SELECT COUNT(*) FROM bedrijven WHERE rechtsvorm_code = ?", (RECHTSVORM,)
    ).fetchone()[0]
    target = min(total_bv, limit) if limit else total_bv
    print(f"BV companies in source: {total_bv:,} — importing {target:,}")

    print("Building temporary index on vestigingen(kvk_nummer)…")
    build_temp_index(source)

    stream = source.cursor()
    stream.execute(
        "SELECT kvk_nummer, naam, statutaire_naam FROM bedrijven "
        "WHERE rechtsvorm_code = ?",
        (RECHTSVORM,),
    )

    started = time.monotonic()
    seen = 0
    inserted = 0
    while True:
        if limit is not None and seen >= limit:
            break
        take = batch_size if limit is None else min(batch_size, limit - seen)
        batch = stream.fetchmany(take)
        if not batch:
            break
        seen += len(batch)
        async with engine.begin() as conn:
            inserted += await import_batch(conn, batch, source)
        if seen % (batch_size * 10) == 0:
            elapsed = time.monotonic() - started
            rate = seen / elapsed if elapsed else 0
            print(
                f"  {seen:,}/{target:,} processed · {inserted:,} new "
                f"({rate:,.0f}/s)",
                flush=True,
            )

    source.close()
    await engine.dispose()
    elapsed = time.monotonic() - started
    print(
        f"Done. Processed {seen:,} BV companies, inserted {inserted:,} new "
        f"(skipped {seen - inserted:,} already present) in {elapsed:,.0f}s."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=DEFAULT_SQLITE, help="path to the KVK SQLite dump")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None, help="cap companies (smoke test)")
    args = parser.parse_args()
    asyncio.run(run(args.sqlite, args.batch_size, args.limit))


if __name__ == "__main__":
    main()
