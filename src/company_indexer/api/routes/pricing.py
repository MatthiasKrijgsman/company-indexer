from typing import Any

from fastapi import APIRouter

from company_indexer import pricing

router = APIRouter(tags=["pricing"])


@router.get("/pricing")
async def get_pricing() -> dict[str, Any]:
    """Provider rate card + per-action EUR estimates for the cost indicator.

    Static — derived from the configured ``USD_TO_EUR`` rate and the provider
    rates in ``pricing.py``. The frontend shows the estimates next to each
    enrichment action; actual costs are persisted per row at run time.
    """
    return pricing.pricing_overview()
