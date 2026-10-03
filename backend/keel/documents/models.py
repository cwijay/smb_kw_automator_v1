import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from keel.platform.db import Base
from keel.platform.ids import uuid7

DOC_KINDS = ("order_pad", "supplier_invoice", "batch_sheet", "haccp_log", "other", "unknown")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    kind: Mapped[str] = mapped_column(default="unknown")
    filename: Mapped[str]
    mime: Mapped[str]
    size_bytes: Mapped[int]
    sha256: Mapped[str]
    storage_key: Mapped[str]
    source: Mapped[str] = mapped_column(default="upload")
    status: Mapped[str] = mapped_column(default="uploaded")
    page_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None]
    created_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    n: Mapped[int]
    image_key: Mapped[str]
    width: Mapped[int]
    height: Mapped[int]
    has_text_layer: Mapped[bool] = mapped_column(default=False)
    words: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    schema_name: Mapped[str]
    engine: Mapped[str]
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    cost_usd: Mapped[Decimal] = mapped_column(default=Decimal(0))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class FieldResult(Base):
    __tablename__ = "field_results"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    extraction_id: Mapped[uuid.UUID | None]
    page_id: Mapped[uuid.UUID | None]
    path: Mapped[str]
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    status: Mapped[str]
    confidence: Mapped[float] = mapped_column(default=0.0)
    engine: Mapped[str]
    corrected_by: Mapped[uuid.UUID | None]
    corrected_at: Mapped[datetime | None]


class FieldCitation(Base):
    __tablename__ = "field_citations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    field_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("field_results.id"))
    page_id: Mapped[uuid.UUID]
    x: Mapped[float]
    y: Mapped[float]
    w: Mapped[float]
    h: Mapped[float]
    text: Mapped[str] = mapped_column(default="")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    page_n: Mapped[int]
    text: Mapped[str]
