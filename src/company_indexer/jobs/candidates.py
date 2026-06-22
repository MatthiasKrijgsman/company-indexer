"""Candidate careers URLs from homepage HTML.

Includes the company's own pages **and** external careers links — a
``werkenbij`` subdomain, a dedicated werkenbij domain, or an ATS host
(Recruitee, Homerun, …). External links are admitted on list-free signals
(same registrable domain, a careers keyword in the host, or a strongly
careers-labelled anchor), so detection does not depend on a maintained ATS
list. A tiny ATS seed only nudges scoring; the LLM resolver is the final judge
of whether an external page is really this company's careers page.
"""

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from company_indexer.scraper.discover import normalize_url

MAX_CANDIDATES = 10
MAX_EXTERNAL = 5  # cap so a link-heavy footer can't crowd out on-domain matches

# (keyword, weight). Substring match on lowercased host + path + anchor text.
_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("vacature", 6),
    ("vacatures", 6),
    ("werkenbij", 6),
    ("werken-bij", 5),
    ("werken", 3),
    ("careers", 5),
    ("career", 4),
    ("jobs", 5),
    ("job", 3),
)

# Keywords that, when present in the *host*, mark an off-domain link as a
# careers page on their own (e.g. werkenbijacme.nl, acme-careers.com).
_HOST_KEYWORDS: tuple[str, ...] = (
    "werkenbij",
    "werken-bij",
    "vacature",
    "vacatures",
    "careers",
    "jobs",
)

# Anchor/path score at or above this strongly implies a careers page even when
# the host is generic (an ATS we don't recognize) — e.g. a nav link "Vacatures".
_STRONG_SCORE = 5

# Tiny ATS seed — a *hint* that admits/boosts, never a gate. The list-free
# signals above plus the LLM judge handle the long tail, so an incomplete seed
# never blocks a resolution. (At scale this set can be grown automatically from
# resolved-careers history — see VISION.md roadmap.)
_ATS_HOST_SUFFIXES: tuple[str, ...] = (
    "recruitee.com",
    "homerun.co",
    "homerun.com",
    "greenhouse.io",
    "lever.co",
    "workable.com",
    "personio.com",
    "personio.de",
    "teamtailor.com",
    "smartrecruiters.com",
    "join.com",
)

_FALLBACK_PATHS: tuple[str, ...] = ("/vacatures", "/werken-bij", "/careers")


@dataclass(frozen=True)
class Candidate:
    url: str
    anchor_text: str
    score: int
    is_external: bool = False


def _registrable(host: str) -> str:
    """eTLD+1 via the last two labels. Correct for .nl/.com/.be and the like;
    a known simplification for multi-part TLDs (e.g. .co.uk). Good enough for
    Dutch SMBs and avoids a public-suffix-list dependency."""
    labels = host.lower().split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host.lower()


def _is_ats_host(host: str) -> bool:
    return any(host == s or host.endswith(f".{s}") for s in _ATS_HOST_SUFFIXES)


def _host_has_keyword(host: str) -> bool:
    return any(kw in host for kw in _HOST_KEYWORDS)


def _same_site(host: str, base_host: str) -> bool:
    """Apex <-> www of the exact same host."""
    if host == base_host:
        return True
    return host == f"www.{base_host}" or base_host == f"www.{host}"


def _score(host: str, path: str, anchor_text: str) -> int:
    combined = f"{host} {path} {anchor_text}".lower()
    return sum(weight for kw, weight in _KEYWORDS if kw in combined)


def build_candidates(homepage_html: str, homepage_url: str) -> list[Candidate]:
    """Extract up to ``MAX_CANDIDATES`` careers-URL candidates from the homepage,
    including qualifying external (werkenbij / ATS) links."""
    base_host = urlparse(homepage_url).netloc.lower()
    base_reg = _registrable(base_host)
    homepage_norm = normalize_url(homepage_url)

    best: dict[str, Candidate] = {}

    if homepage_html:
        soup = BeautifulSoup(homepage_html, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urljoin(homepage_url, href)
            host = urlparse(absolute).netloc.lower()
            if not host:
                continue

            normalized = normalize_url(absolute)
            if normalized == homepage_norm:
                continue

            text = link.get_text(" ", strip=True)
            path = urlparse(absolute).path
            anchor_path_score = _score("", path, text)

            same = _same_site(host, base_host)
            if same:
                if anchor_path_score <= 0:
                    continue
                score = anchor_path_score
                is_external = False
            else:
                # Off-domain: admit only on a real careers signal (list-free).
                same_reg = _registrable(host) == base_reg
                eligible = (
                    same_reg
                    or _host_has_keyword(host)
                    or anchor_path_score >= _STRONG_SCORE
                    or _is_ats_host(host)
                )
                if not eligible:
                    continue
                score = _score(host, path, text)
                if _is_ats_host(host):
                    score += 4  # seed hint nudge
                if score <= 0:
                    continue
                is_external = True

            prior = best.get(normalized)
            if prior is None or score > prior.score:
                best[normalized] = Candidate(
                    url=absolute,
                    anchor_text=text,
                    score=score,
                    is_external=is_external,
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

    # Keep all on-domain candidates; cap externals so a link-heavy footer can't
    # crowd them out. On-domain keeps priority via the score sort.
    result: list[Candidate] = []
    external_kept = 0
    for c in ranked:
        if c.is_external:
            if external_kept >= MAX_EXTERNAL:
                continue
            external_kept += 1
        result.append(c)
        if len(result) >= MAX_CANDIDATES:
            break
    return result
