from dataclasses import dataclass
from typing import Any

import httpx

SERPER_URL = "https://google.serper.dev/search"
DEFAULT_TIMEOUT = 15.0


@dataclass
class SerperResult:
    ok: bool
    results: dict[str, Any] | None = None
    error: str | None = None


async def search(query: str, api_key: str) -> SerperResult:
    """Call Serper's /search endpoint.

    Returns a ``SerperResult`` — never raises for HTTP errors. ``error`` is a
    short, stable code the route can persist: ``no_credits``, ``unauthorized``,
    ``http_{status}``, ``timeout``, ``network_error``.
    """
    payload = {"q": query, "num": 20}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(SERPER_URL, json=payload, headers=headers)
    except httpx.TimeoutException:
        return SerperResult(ok=False, error="timeout")
    except httpx.HTTPError:
        return SerperResult(ok=False, error="network_error")

    if response.status_code == 200:
        return SerperResult(ok=True, results=response.json())
    if response.status_code in (402, 403):
        # Serper returns 402/403 when the account is out of credits or the
        # key is rejected. The body distinguishes them but we only need a
        # stable code for downstream filtering.
        body = response.text.lower()
        if "credit" in body or response.status_code == 402:
            return SerperResult(ok=False, error="no_credits")
        return SerperResult(ok=False, error="unauthorized")
    return SerperResult(ok=False, error=f"http_{response.status_code}")
