from datetime import datetime

from pydantic import BaseModel, ConfigDict

from company_indexer.models import WebsiteConfidence


class WebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_search_id: int
    url: str | None
    confidence: WebsiteConfidence
    reason: str
    llm_model: str
    created_at: datetime
