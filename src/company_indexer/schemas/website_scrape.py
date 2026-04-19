from datetime import datetime

from pydantic import BaseModel, ConfigDict

from company_indexer.models import (
    WebsitePageFetchMethod,
    WebsitePageStatus,
    WebsiteScrapeStatus,
)


class WebsitePageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    normalized_url: str
    fetch_method: WebsitePageFetchMethod
    status: WebsitePageStatus
    http_status: int | None
    content_type: str | None
    content_hash: str | None
    title: str | None
    markdown: str | None
    fetched_at: datetime


class WebsiteScrapeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_website_id: int
    status: WebsiteScrapeStatus
    pages_attempted: int
    pages_ok: int
    pages_failed: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime
    pages: list[WebsitePageRead]
