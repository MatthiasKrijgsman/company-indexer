"""JS-skeleton and WAF-block heuristics on a fetched response.

Called after every Tier-1 fetch. Produces a ``Verdict`` that the orchestrator
maps to a ``WebsitePageStatus``. Slice 1 only records the verdict; slice 2
uses it to route the URL to a Tier-2 provider.
"""

import re
from dataclasses import dataclass
from typing import Literal

from company_indexer.scraper.fetch import FetchResult

Verdict = Literal["ok", "js_required", "blocked"]


@dataclass
class DetectResult:
    verdict: Verdict
    reason: str | None = None


_BLOCK_MARKERS = (
    "cf-chl",
    "__cf_bm",
    "challenge-platform",
    "datadome",
    "px-captcha",
    "captcha-delivery",
)

_JS_ROOT_IDS = ('id="root"', 'id="app"', 'id="__next"', 'id="__nuxt"')

_JS_NOSCRIPT = re.compile(r"<noscript[^>]*>[^<]*enable\s+javascript", re.IGNORECASE)

_META_REFRESH = re.compile(r'<meta\s+http-equiv=["\']refresh["\']', re.IGNORECASE)

_WINDOW_LOCATION = re.compile(r"window\.location", re.IGNORECASE)

# Rough heuristic: strip tags and see how much visible text is left. Avoids
# pulling in BeautifulSoup just for this.
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)


def _visible_text_length(html: str) -> int:
    stripped = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", stripped)
    return len(text.strip())


def detect(result: FetchResult) -> DetectResult:
    """Classify a Tier-1 response.

    Only examines responses the caller considers "got something back" — i.e.
    ``result.html`` is populated. For pure transport errors (timeout, DNS)
    the orchestrator doesn't call this.
    """
    html = result.html or ""
    lowered = html.lower()

    if result.status in (403, 503) and any(m in lowered for m in _BLOCK_MARKERS):
        return DetectResult(verdict="blocked", reason="waf_markers")

    if result.status == 200:
        for marker in _JS_ROOT_IDS:
            if marker in html and _visible_text_length(html) < 200:
                return DetectResult(verdict="js_required", reason="js_skeleton")

        if len(html) < 2048 and _JS_NOSCRIPT.search(html):
            return DetectResult(verdict="js_required", reason="noscript_notice")

        if _META_REFRESH.search(html) and _visible_text_length(html) < 200:
            return DetectResult(verdict="js_required", reason="meta_refresh")

        if _WINDOW_LOCATION.search(html) and _visible_text_length(html) < 200:
            return DetectResult(verdict="js_required", reason="js_redirect")

    return DetectResult(verdict="ok")
