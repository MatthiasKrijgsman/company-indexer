import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from company_indexer.db import Base
from company_indexer.models.company import Company
from company_indexer.models.website_search import WebsiteSearch


class WebsiteConfidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


website_confidence_enum = Enum(
    WebsiteConfidence,
    name="website_confidence",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class CompanyWebsite(Base):
    __tablename__ = "company_websites"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_search_id: Mapped[int] = mapped_column(
        ForeignKey("website_searches.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    confidence: Mapped[WebsiteConfidence] = mapped_column(website_confidence_enum)
    reason: Mapped[str] = mapped_column(String(1024))
    llm_model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship()
    source_search: Mapped[WebsiteSearch] = relationship()
