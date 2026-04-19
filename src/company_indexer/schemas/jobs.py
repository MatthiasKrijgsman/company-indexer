from datetime import datetime

from pydantic import BaseModel, ConfigDict

from company_indexer.models import (
    JobEmploymentType,
    JobsScrapeStatus,
    WebsiteConfidence,
)


class CompanyCareersUrlRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_scrape_id: int
    url: str | None
    confidence: WebsiteConfidence
    reason: str
    llm_model: str
    created_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: str | None
    location: str | None
    employment_type: JobEmploymentType
    department: str | None
    raw_snippet: str | None
    created_at: datetime


class JobsScrapeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_careers_id: int
    fetched_url: str
    status: JobsScrapeStatus
    http_status: int | None
    content_hash: str | None
    llm_model: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime
    jobs: list[JobRead]
