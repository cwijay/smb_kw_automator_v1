import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ARRAY, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from keel.platform.db import Base
from keel.platform.ids import uuid7


class Formula(Base):
    __tablename__ = "formulas"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    batch_size: Mapped[Decimal]
    unit: Mapped[str]
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Lot(Base):
    __tablename__ = "lots"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    code: Mapped[str]
    kind: Mapped[str]
    product_id: Mapped[uuid.UUID | None]
    ingredient: Mapped[str | None]
    supplier: Mapped[str | None]
    quantity: Mapped[Decimal | None]
    unit: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    number: Mapped[str]
    product_id: Mapped[uuid.UUID | None]
    output_lot_id: Mapped[uuid.UUID | None]
    made_on: Mapped[date | None]
    quantity: Mapped[Decimal | None]
    unit: Mapped[str | None]
    prepared_by: Mapped[str | None]
    source_document_id: Mapped[uuid.UUID | None]
    approval_id: Mapped[uuid.UUID | None]
    signed_off_by: Mapped[uuid.UUID | None]
    version: Mapped[int] = mapped_column(default=1)
    supersedes: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BatchInput(Base):
    __tablename__ = "batch_inputs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"))
    lot_id: Mapped[uuid.UUID | None]
    ingredient: Mapped[str]
    quantity: Mapped[Decimal | None]
    unit: Mapped[str | None]
    status: Mapped[str]


class CcpDefinition(Base):
    __tablename__ = "ccp_definitions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    name: Mapped[str]
    min_value: Mapped[Decimal | None]
    max_value: Mapped[Decimal | None]
    unit: Mapped[str]
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class HaccpReading(Base):
    __tablename__ = "haccp_readings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    ccp_id: Mapped[uuid.UUID | None]
    ccp_as_written: Mapped[str]
    batch_number: Mapped[str | None]
    value: Mapped[Decimal | None]
    unit: Mapped[str | None]
    status: Mapped[str]
    recorded_on: Mapped[date | None]
    recorded_at_time: Mapped[str | None]
    operator: Mapped[str | None]
    source_document_id: Mapped[uuid.UUID | None]
    approval_id: Mapped[uuid.UUID | None]
    verified_by: Mapped[uuid.UUID | None]
    version: Mapped[int] = mapped_column(default=1)
    supersedes: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    reading_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("haccp_readings.id"))
    action: Mapped[str]
    recorded_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Allocation(Base):
    __tablename__ = "allocations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    order_line_id: Mapped[uuid.UUID]
    lot_id: Mapped[uuid.UUID]
    quantity: Mapped[Decimal | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
