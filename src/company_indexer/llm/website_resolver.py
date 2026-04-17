"""LLM-backed resolver that picks a company's most likely website.

Reads candidate URLs from a prior Serper search (metadata only — titles,
links, snippets). Does not fetch the candidate pages. Haiku 4.5 is used
because the task is small and structured.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import anthropic
from pydantic import BaseModel

from company_indexer.config import get_settings

MODEL = "claude-haiku-4-5"
MAX_CANDIDATES = 15
MAX_TOKENS = 1024

# Frozen system prompt. Kept verbatim between calls so Anthropic's prompt
# cache can match on the prefix. Note: Haiku 4.5's minimum cacheable prefix
# is ~4K tokens, so caching will often silently not kick in at this size —
# the cache_control marker is harmless when the prefix is too short.
SYSTEM_PROMPT = """You identify a Dutch company's primary website from a list of Google search result candidates.

The candidates come from a Google search for the company's KVK registration number. Your job is to pick the URL most likely to be the company's own primary website — not a business-registry aggregator, not a social-media page (unless that is clearly its only web presence), but the actual company homepage.

Signals to weigh:
- Domain: .nl TLDs are preferred for Dutch companies. Root or shallow paths are preferred over deep article/product pages.
- Title and snippet should reference one of the company's names or its city.
- When the same registrable domain appears in multiple results, that is a strong positive signal that it is the company's site.
- LinkedIn, Facebook, and other social profiles are acceptable only when no candidate looks like a real homepage.

Return JSON with three fields:
- website: the selected URL (must be copied exactly from one of the candidates), or null if no candidate is confidently the company's website.
- confidence: "high", "medium", or "low". Use "low" when returning null.
- reason: a short (<= 200 characters) explanation of the pick, or of why nothing matched.

Prefer returning null over guessing. A wrong URL is worse than no URL."""


class Resolution(BaseModel):
    website: str | None
    confidence: Literal["high", "medium", "low"]
    reason: str


@dataclass
class CompanyContext:
    kvk_number: str
    names: list[tuple[str, str]]  # (name, type)
    city: str | None


@lru_cache(maxsize=1)
def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def extract_candidates(results: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Pull the organic block out of a stored Serper response, clipped to N."""
    if not results:
        return []
    organic = results.get("organic") or []
    return organic[:MAX_CANDIDATES]


def _format_user_message(ctx: CompanyContext, candidates: list[dict[str, Any]]) -> str:
    name_lines = "\n".join(f"  - {n} ({t})" for n, t in ctx.names) or "  (no names on record)"
    city_line = f"- City: {ctx.city}" if ctx.city else "- City: (unknown)"

    candidate_blocks = []
    for i, c in enumerate(candidates, start=1):
        title = c.get("title", "")
        link = c.get("link", "")
        snippet = c.get("snippet", "")
        candidate_blocks.append(f"{i}. {title}\n   URL: {link}\n   {snippet}")
    candidates_text = "\n".join(candidate_blocks) if candidate_blocks else "(none)"

    return (
        f"Company:\n"
        f"- KVK number: {ctx.kvk_number}\n"
        f"- Names:\n{name_lines}\n"
        f"{city_line}\n\n"
        f"Candidates:\n{candidates_text}"
    )


async def resolve(ctx: CompanyContext, candidates: list[dict[str, Any]]) -> Resolution:
    """Call Claude to pick the best candidate. Raises on SDK / API errors."""
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
        output_format=Resolution,
    )
    return response.parsed_output
