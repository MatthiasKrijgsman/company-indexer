"""Tier 1 fetch: httpx with a real-browser profile.

Returns a FetchResult — never raises on HTTP errors. The caller inspects
``ok`` / ``error`` / ``status`` to decide what to persist.
"""

from dataclasses import dataclass

import httpx

from company_indexer.scraper.headers import BrowserProfile, build_headers

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 20.0


@dataclass
class FetchResult:
    ok: bool
    status: int | None = None
    html: str | None = None
    content_type: str | None = None
    final_url: str | None = None
    error: str | None = None


def build_client(profile: BrowserProfile) -> httpx.AsyncClient:
    """Build a client configured for this scrape.

    Shared across a single company's pages so a session cookie set on the
    homepage is sent with internal-page requests (some sites require this).
    """
    return httpx.AsyncClient(
        http2=True,
        follow_redirects=True,
        timeout=httpx.Timeout(DEFAULT_READ_TIMEOUT, connect=DEFAULT_CONNECT_TIMEOUT),
        headers=build_headers(profile),
    )


async def fetch(client: httpx.AsyncClient, url: str) -> FetchResult:
    response: httpx.Response | None = None
    for attempt in range(2):
        try:
            response = await client.get(url)
        except httpx.TimeoutException:
            if attempt == 0:
                continue
            return FetchResult(ok=False, error="timeout")
        except httpx.ConnectError:
            return FetchResult(ok=False, error="dead_domain")
        except httpx.HTTPError:
            if attempt == 0:
                continue
            return FetchResult(ok=False, error="network_error")
        break

    assert response is not None

    content_type = response.headers.get("content-type", "")
    final_url = str(response.url)

    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return FetchResult(
            ok=False,
            status=response.status_code,
            content_type=content_type,
            final_url=final_url,
            error="non_html",
        )

    if response.status_code >= 500:
        return FetchResult(
            ok=False,
            status=response.status_code,
            html=response.text,
            content_type=content_type,
            final_url=final_url,
            error="http_5xx",
        )
    if response.status_code >= 400:
        return FetchResult(
            ok=False,
            status=response.status_code,
            html=response.text,
            content_type=content_type,
            final_url=final_url,
            error="http_4xx",
        )

    return FetchResult(
        ok=True,
        status=response.status_code,
        html=response.text,
        content_type=content_type,
        final_url=final_url,
    )
