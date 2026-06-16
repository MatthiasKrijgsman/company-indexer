"""Cost accounting for the paid enrichment steps.

The single place provider rates live. Two paid providers incur cost:

- **Serper** (website search) — flat per search. Starter tier is ~$1.00 per
  1,000 searches (1 credit, ``num<=10``).
- **Claude Haiku 4.5** (resolve-website, resolve-careers, scrape-jobs) — priced
  per million tokens, input/output/cache split.

Everything is computed in USD then converted to EUR via a static, configurable
rate (``USD_TO_EUR``, see ``config.py``) — there is no live FX. Amounts are
``Decimal`` quantized to 5 dp to match the ``Numeric(10, 5)`` columns.

Each action also has a pre-run **estimate** built from representative token
counts fed through the same formula, so estimates and actuals stay consistent.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from company_indexer.config import get_settings

# ---- Provider rates (USD) ----

SERPER_USD_PER_SEARCH = 0.001  # ~$1.00 / 1,000 searches (Starter tier)

# Claude Haiku 4.5, USD per million tokens.
HAIKU_USD_PER_MTOK_INPUT = 1.0
HAIKU_USD_PER_MTOK_OUTPUT = 5.0
HAIKU_USD_PER_MTOK_CACHE_WRITE = 1.25
HAIKU_USD_PER_MTOK_CACHE_READ = 0.10

_MTOK = 1_000_000
_CENTI = Decimal("0.00001")  # 5 decimal places


@dataclass
class LlmUsage:
    """Token usage for one LLM call. Cache fields are ~always 0 here — the
    system prompts are below Haiku's 4K cacheable minimum — but the formula
    accounts for them so a future cached prompt is priced correctly."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def usage_from(response: Any) -> LlmUsage:
    """Extract an ``LlmUsage`` from an Anthropic ``messages`` response.

    Defensive: missing fields default to 0 so a provider/SDK shape change
    degrades to a zero/partial cost rather than raising in the request path.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return LlmUsage()
    return LlmUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )


# ---- USD cost ----

def llm_cost_usd(usage: LlmUsage) -> float:
    return (
        usage.input_tokens * HAIKU_USD_PER_MTOK_INPUT
        + usage.output_tokens * HAIKU_USD_PER_MTOK_OUTPUT
        + usage.cache_read_tokens * HAIKU_USD_PER_MTOK_CACHE_READ
        + usage.cache_write_tokens * HAIKU_USD_PER_MTOK_CACHE_WRITE
    ) / _MTOK


def serper_cost_usd() -> float:
    return SERPER_USD_PER_SEARCH


# ---- EUR conversion ----

def to_eur(usd: float) -> Decimal:
    """Convert USD to EUR using the configured static rate, quantized to 5 dp."""
    rate = Decimal(str(get_settings().usd_to_eur))
    return (Decimal(str(usd)) * rate).quantize(_CENTI, rounding=ROUND_HALF_UP)


def llm_cost_eur(usage: LlmUsage) -> Decimal:
    return to_eur(llm_cost_usd(usage))


def serper_cost_eur() -> Decimal:
    return to_eur(serper_cost_usd())


# ---- Pre-run estimates ----

# Representative token counts per LLM action (rough, deliberately generous on
# the input side). Run through the same formula as the actuals.
_ESTIMATE_USAGE: dict[str, LlmUsage] = {
    "resolve_website": LlmUsage(input_tokens=600, output_tokens=80),
    "resolve_careers": LlmUsage(input_tokens=400, output_tokens=60),
    "scrape_jobs": LlmUsage(input_tokens=8000, output_tokens=500),
}

# All enrichment actions and how they're costed. Free steps estimate to 0.
ACTIONS: tuple[str, ...] = (
    "website_search",
    "resolve_website",
    "scrape",
    "resolve_careers",
    "scrape_jobs",
    "geocode",
)


def estimate_eur(action: str) -> Decimal:
    if action == "website_search":
        return serper_cost_eur()
    if action in _ESTIMATE_USAGE:
        return llm_cost_eur(_ESTIMATE_USAGE[action])
    # scrape, geocode, or unknown → free
    return Decimal("0.00000")


def pricing_overview() -> dict[str, Any]:
    """Payload for ``GET /pricing`` — the rate card + per-action estimates."""
    return {
        "usd_to_eur": get_settings().usd_to_eur,
        "rates_usd": {
            "serper_per_search": SERPER_USD_PER_SEARCH,
            "haiku_per_mtok_input": HAIKU_USD_PER_MTOK_INPUT,
            "haiku_per_mtok_output": HAIKU_USD_PER_MTOK_OUTPUT,
        },
        "estimates_eur": {action: str(estimate_eur(action)) for action in ACTIONS},
    }
