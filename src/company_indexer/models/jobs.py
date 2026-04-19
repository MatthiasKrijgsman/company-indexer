import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from company_indexer.db import Base
from company_indexer.models.company import Company
from company_indexer.models.company_website import WebsiteConfidence, website_confidence_enum
from company_indexer.models.website_scrape import WebsiteScrape


class JobsScrapeStatus(str, enum.Enum):
    OK = "ok"
    NO_JOBS = "no_jobs"
    NO_CAREERS_PAGE = "no_careers_page"
    JS_REQUIRED = "js_required"
    BLOCKED = "blocked"
    FAILED = "failed"
    LLM_ERROR = "llm_error"


jobs_scrape_status_enum = Enum(
    JobsScrapeStatus,
    name="jobs_scrape_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class JobEmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


job_employment_type_enum = Enum(
    JobEmploymentType,
    name="job_employment_type",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class CompanyCareersUrl(Base):
    __tablename__ = "company_careers_urls"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_scrape_id: Mapped[int] = mapped_column(
        ForeignKey("website_scrapes.id", ondelete="CASCADE")
    )
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    confidence: Mapped[WebsiteConfidence] = mapped_column(website_confidence_enum)
    reason: Mapped[str] = mapped_column(String(512))
    llm_model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship()
    source_scrape: Mapped[WebsiteScrape] = relationship()


class JobsScrape(Base):
    __tablename__ = "jobs_scrapes"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_careers_id: Mapped[int] = mapped_column(
        ForeignKey("company_careers_urls.id", ondelete="CASCADE")
    )
    fetched_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[JobsScrapeStatus] = mapped_column(jobs_scrape_status_enum)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    html_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship()
    source_careers: Mapped[CompanyCareersUrl] = relationship()
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="jobs_scrape",
        cascade="all, delete-orphan",
        order_by="Job.id",
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    jobs_scrape_id: Mapped[int] = mapped_column(
        ForeignKey("jobs_scrapes.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[JobEmploymentType] = mapped_column(job_employment_type_enum)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_snippet: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    jobs_scrape: Mapped[JobsScrape] = relationship(back_populates="jobs")
