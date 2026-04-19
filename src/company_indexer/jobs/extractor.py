"""LLM-backed extraction of job postings from a careers page.

Input: markdown of one careers page (already fetched + extracted by the
scraper pipeline). Output: a list of structured ``JobItem`` records.
"""

from functools import lru_cache
from typing import Literal

import anthropic
from pydantic import BaseModel

from company_indexer.config import get_settings
from company_indexer.jobs.resolver import CompanyContext

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 4096

# Keep the markdown small enough that extraction fits comfortably within the
# input window and Haiku doesn't pay a long-context penalty. Real careers
# pages rarely need more than this; if they do we'd rather truncate and miss
# a few jobs than OOM the call.
MAX_MARKDOWN_CHARS = 30000

SYSTEM_PROMPT = """You extract open job postings from a company's careers page.

You receive:
- A short description of the company (name, city, homepage).
- The extracted markdown of one careers page from the company's website.

Your job is to return every open position listed on the page. Each posting becomes one entry in the list.

Rules:
- Only return postings that are clearly open roles on this company. Skip testimonials, team member bios, blog posts about culture, "past roles", and newsletter sign-ups.
- If the page clearly states there are no open roles at this time (e.g. "Op dit moment hebben we geen openstaande vacatures"), return an empty list.
- title: the role title exactly as written.
- url: the URL of the per-posting detail page if the page links to one, otherwise null. Copy it verbatim; do not invent URLs.
- location: the role's location if stated (e.g. "Amsterdam", "Remote (NL)"). Null if absent.
- employment_type: one of "full_time", "part_time", "contract", "internship", "unknown". Use "unknown" when the page doesn't say.
- department: the department/team if stated (e.g. "Engineering", "Sales"). Null if absent.
- raw_snippet: a short (<= 400 chars) verbatim markdown fragment from which you extracted this job. Used for debugging.

Prefer precision over recall. An empty list is correct when the page is about the company more broadly than open roles."""


class JobItem(BaseModel):
    title: str
    url: str | None
    location: str | None
    employment_type: Literal[
        "full_time", "part_time", "contract", "internship", "unknown"
    ]
    department: str | None
    raw_snippet: str | None


class JobExtraction(BaseModel):
    jobs: list[JobItem]


@lru_cache(maxsize=1)
def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _format_user_message(
    ctx: CompanyContext, careers_url: str, markdown: str
) -> str:
    name_lines = (
        "\n".join(f"  - {n} ({t})" for n, t in ctx.names)
        or "  (no names on record)"
    )
    city_line = f"- City: {ctx.city}" if ctx.city else "- City: (unknown)"
    clipped = markdown[:MAX_MARKDOWN_CHARS]
    return (
        f"Company:\n"
        f"- Homepage: {ctx.homepage_url}\n"
        f"- Names:\n{name_lines}\n"
        f"{city_line}\n\n"
        f"Careers page URL: {careers_url}\n\n"
        f"Careers page markdown:\n{clipped}"
    )


async def extract_jobs(
    ctx: CompanyContext, careers_url: str, markdown: str
) -> list[JobItem]:
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
        messages=[
            {
                "role": "user",
                "content": _format_user_message(ctx, careers_url, markdown),
            }
        ],
        output_format=JobExtraction,
    )
    return response.parsed_output.jobs
