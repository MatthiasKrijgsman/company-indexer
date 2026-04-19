"""Candidate careers URLs from homepage HTML.

Same-domain only. Cross-domain links (ATS hosts) are intentionally
dropped in slice 1 — a company with no same-domain careers page is
recorded as "no careers page" for now.
"""

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from company_indexer.scraper.discover import normalize_url

MAX_CANDIDATES = 10

# (keyword, weight). Substring match on lowercased path + anchor text.
_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("vacature", 6),
    ("vacatures", 6),
    ("werken-bij", 5),
    ("werken", 3),
    ("careers", 5),
    ("career", 4),
    ("jobs", 5),
    ("job", 3),
)

_FALLBACK_PATHS: tuple[str, ...] = ("/vacatures", "/werken-bij", "/careers")


@dataclass(frozen=True)
class Candidate:
    url: str
    anchor_text: str
    score: int


def _same_domain(url: str, base_host: str) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False
    if host == base_host:
        return True
    # Treat apex <-> www as same site; no broader subdomain matching here
    # since ATS subdomains live on *other* registrable domains anyway.
    return host == f"www.{base_host}" or base_host == f"www.{host}"


def _score(path: str, anchor_text: str) -> int:
    combined = f"{path} {anchor_text}".lower()
    return sum(weight for kw, weight in _KEYWORDS if kw in combined)


def build_candidates(homepage_html: str, homepage_url: str) -> list[Candidate]:
    """Extract up to ``MAX_CANDIDATES`` careers-URL candidates from the homepage."""
    base_host = urlparse(homepage_url).netloc.lower()
    homepage_norm = normalize_url(homepage_url)

    best: dict[str, Candidate] = {}

    if homepage_html:
        soup = BeautifulSoup(homepage_html, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urljoin(homepage_url, href)
            if not _same_domain(absolute, base_host):
                continue
            normalized = normalize_url(absolute)
            if normalized == homepage_norm:
                continue
            text = link.get_text(" ", strip=True)
            score = _score(urlparse(absolute).path, text)
            if score <= 0:
                continue
            prior = best.get(normalized)
            if prior is None or score > prior.score:
                best[normalized] = Candidate(
                    url=absolute, anchor_text=text, score=score
                )

    # Fallback paths on the company's own domain. Scored at 1 so real link
    # matches win when present.
    fallback_prefix = f"{urlparse(homepage_url).scheme}://{base_host}"
    for path in _FALLBACK_PATHS:
        absolute = fallback_prefix + path
        normalized = normalize_url(absolute)
        if normalized == homepage_norm or normalized in best:
            continue
        best[normalized] = Candidate(url=absolute, anchor_text="", score=1)

    ranked = sorted(best.values(), key=lambda c: c.score, reverse=True)
    return ranked[:MAX_CANDIDATES]
