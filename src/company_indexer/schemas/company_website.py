from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from company_indexer.models import WebsiteConfidence


class WebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_search_id: int
    url: str | None
    homepage_url: str | None
    confidence: WebsiteConfidence
    reason: str
    llm_model: str
    cost_eur: Decimal | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
