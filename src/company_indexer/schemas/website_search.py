from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from company_indexer.models import WebsiteSearchStatus


class WebsiteSearchDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    status: WebsiteSearchStatus
    error: str | None
    results: dict[str, Any] | None
    created_at: datetime
