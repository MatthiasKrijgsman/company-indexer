"""PDOK Locatieserver geocoding client.

Free, keyless geocoding for Dutch addresses, backed by the BAG registry.
Docs: https://api.pdok.nl/bzk/locatieserver
"""

import re
from dataclasses import dataclass

import httpx

PDOK_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
DEFAULT_TIMEOUT = 10.0

# centroide_ll comes back as WGS84 WKT: "POINT(<lon> <lat>)". Note lon-then-lat.
_WKT_POINT = re.compile(r"POINT\(([-\d.]+)\s+([-\d.]+)\)")


@dataclass
class GeocodeResult:
    ok: bool
    lat: float | None = None
    lon: float | None = None
    match_type: str | None = None
    error: str | None = None


def _parse_centroide_ll(wkt: str) -> tuple[float, float] | None:
    m = _WKT_POINT.match(wkt)
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return lat, lon


async def geocode(query: str) -> GeocodeResult:
    """Look up a Dutch address. Only accepts address-level matches (``type=adres``).

    Never raises for HTTP errors — the caller inspects ``ok`` and ``error``.
    Stable error codes: ``no_match``, ``timeout``, ``network_error``,
    ``http_{status}``, ``parse_error``.
    """
    params = {"q": query, "fq": "type:adres", "rows": 1}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(PDOK_URL, params=params)
    except httpx.TimeoutException:
        return GeocodeResult(ok=False, error="timeout")
    except httpx.HTTPError:
        return GeocodeResult(ok=False, error="network_error")

    if response.status_code != 200:
        return GeocodeResult(ok=False, error=f"http_{response.status_code}")

    data = response.json()
    docs = (data.get("response") or {}).get("docs") or []
    if not docs:
        return GeocodeResult(ok=False, error="no_match")

    doc = docs[0]
    if doc.get("type") != "adres":
        return GeocodeResult(ok=False, error="no_match")

    wkt = doc.get("centroide_ll")
    parsed = _parse_centroide_ll(wkt) if wkt else None
    if parsed is None:
        return GeocodeResult(ok=False, error="parse_error")

    lat, lon = parsed
    return GeocodeResult(ok=True, lat=lat, lon=lon, match_type="adres")
