"""LLM-backed picker for the careers URL.

Given candidate URLs built from the homepage, Haiku picks the most
likely careers/vacatures page — or returns null when none of the
candidates look right.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

import anthropic
from pydantic import BaseModel

from company_indexer.config import get_settings
from company_indexer.jobs.candidates import Candidate
from company_indexer.pricing import LlmUsage, usage_from

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 512

SYSTEM_PROMPT = """You identify a Dutch company's careers / vacancies page from a list of link candidates taken from the company's homepage.

Your job is to pick the single URL most likely to be the page where this company's open job positions are listed — typically titled "Vacatures", "Werken bij", "Careers", "Jobs", "Over/werken", or similar.

Candidates may be on the company's own website OR external. A careers page often lives off the main domain — a "werkenbij" subdomain (e.g. werkenbij.acme.nl), a dedicated werkenbij domain (e.g. werkenbijacme.nl), or an applicant-tracking system / job board the company uses (Recruitee, Homerun, Workable, Greenhouse, Lever, Personio, Teamtailor, and similar). Each candidate is tagged "[same-site]" or "[external: <host>]". An external page is a valid pick when it clearly hosts THIS company's vacancies.

Signals to weigh:
- Anchor text and URL path are both informative. "Vacatures" in the anchor is a stronger signal than the path alone.
- Prefer listing/index pages over deep article pages. A path like /vacatures or /werken-bij scores higher than /nieuws/we-zoeken-een-developer.
- For external candidates, prefer those clearly tied to this company (its name in the host or path, or a known ATS). Be cautious: do NOT pick unrelated third-party links such as generic social profiles, partner sites, cookie/login/portal pages, or a job board's homepage that isn't scoped to this company.
- If candidates are all generic ("/over-ons", "/team") with no clear careers marker, return null.

Return JSON with three fields:
- chosen_url: the selected URL (must be copied exactly from one of the candidates), or null if no candidate is confidently a careers page.
- confidence: "high", "medium", or "low". Use "low" when returning null.
- reason: a short (<= 200 characters) explanation of the pick, or of why nothing matched.

Prefer returning null over guessing. A wrong URL wastes a downstream scrape."""


class CareersPick(BaseModel):
    chosen_url: str | None
    confidence: Literal["high", "medium", "low"]
    reason: str


@dataclass
class CompanyContext:
    kvk_number: str
    names: list[tuple[str, str]]  # (name, type)
    city: str | None
    homepage_url: str


@lru_cache(maxsize=1)
def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _format_user_message(
    ctx: CompanyContext, candidates: list[Candidate]
) -> str:
    name_lines = (
        "\n".join(f"  - {n} ({t})" for n, t in ctx.names)
        or "  (no names on record)"
    )
    city_line = f"- City: {ctx.city}" if ctx.city else "- City: (unknown)"

    if not candidates:
        candidates_text = "(none)"
    else:
        blocks = []
        for i, c in enumerate(candidates, start=1):
            anchor = c.anchor_text or "(no anchor text)"
            origin = f"[external: {urlparse(c.url).netloc}]" if c.is_external else "[same-site]"
            blocks.append(
                f"{i}. {origin} {c.url}\n   anchor: {anchor}\n   score: {c.score}"
            )
        candidates_text = "\n".join(blocks)

    return (
        f"Company:\n"
        f"- KVK number: {ctx.kvk_number}\n"
        f"- Homepage: {ctx.homepage_url}\n"
        f"- Names:\n{name_lines}\n"
        f"{city_line}\n\n"
        f"Candidates:\n{candidates_text}"
    )


async def pick_careers_url(
    ctx: CompanyContext, candidates: list[Candidate]
) -> tuple[CareersPick, LlmUsage]:
    """Call Claude to pick the best candidate. Raises on SDK / API errors.

    Returns the parsed pick plus the call's token usage (for cost accounting).
    """
    client = _get_client()
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": _format_user_message(ctx, candidates)}],
        output_format=CareersPick,
    )
    return response.parsed_output, usage_from(response)
