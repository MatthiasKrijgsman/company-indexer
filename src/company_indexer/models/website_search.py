import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from company_indexer.db import Base
from company_indexer.models.company import Company


class WebsiteSearchStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


website_search_status_enum = Enum(
    WebsiteSearchStatus,
    name="website_search_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class WebsiteSearch(Base):
    __tablename__ = "website_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(String(512))
    status: Mapped[WebsiteSearchStatus] = mapped_column(website_search_status_enum)
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship()
