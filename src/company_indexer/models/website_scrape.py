import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from company_indexer.db import Base
from company_indexer.models.company import Company
from company_indexer.models.company_website import CompanyWebsite


class WebsiteScrapeStatus(str, enum.Enum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED_NO_WEBSITE = "skipped_no_website"
    SKIPPED_JS_HEAVY = "skipped_js_heavy"
    SKIPPED_DEAD_DOMAIN = "skipped_dead_domain"


website_scrape_status_enum = Enum(
    WebsiteScrapeStatus,
    name="website_scrape_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class WebsitePageFetchMethod(str, enum.Enum):
    HTTP = "http"
    JINA = "jina"
    FIRECRAWL = "firecrawl"
    PLAYWRIGHT = "playwright"


website_page_fetch_method_enum = Enum(
    WebsitePageFetchMethod,
    name="website_page_fetch_method",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class WebsitePageStatus(str, enum.Enum):
    OK = "ok"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    JS_REQUIRED = "js_required"
    BLOCKED = "blocked"
    DEAD_DOMAIN = "dead_domain"
    NON_HTML = "non_html"


website_page_status_enum = Enum(
    WebsitePageStatus,
    name="website_page_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class WebsiteScrape(Base):
    __tablename__ = "website_scrapes"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_website_id: Mapped[int] = mapped_column(
        ForeignKey("company_websites.id", ondelete="CASCADE")
    )
    status: Mapped[WebsiteScrapeStatus] = mapped_column(website_scrape_status_enum)
    pages_attempted: Mapped[int] = mapped_column(Integer, default=0)
    pages_ok: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship()
    source_website: Mapped[CompanyWebsite] = relationship()
    pages: Mapped[list["WebsitePage"]] = relationship(
        back_populates="scrape",
        cascade="all, delete-orphan",
        order_by="WebsitePage.id",
    )


class WebsitePage(Base):
    __tablename__ = "website_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    scrape_id: Mapped[int] = mapped_column(
        ForeignKey("website_scrapes.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    normalized_url: Mapped[str] = mapped_column(String(2048))
    fetch_method: Mapped[WebsitePageFetchMethod] = mapped_column(
        website_page_fetch_method_enum
    )
    status: Mapped[WebsitePageStatus] = mapped_column(website_page_status_enum)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    markdown: Mapped[str | None] = mapped_column(nullable=True)
    html_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    scrape: Mapped[WebsiteScrape] = relationship(back_populates="pages")


Index(
    "ix_website_pages_scrape_normalized_url",
    WebsitePage.scrape_id,
    WebsitePage.normalized_url,
    unique=True,
)

# Supports future cross-scrape change-detection queries: "has the content at
# URL X changed since last scrape?" company_id is reached via website_scrapes.
Index(
    "ix_website_pages_url_hash",
    WebsitePage.url,
    WebsitePage.content_hash,
)
