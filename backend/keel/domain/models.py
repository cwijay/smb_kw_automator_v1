import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ARRAY, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from keel.platform.db import Base
from keel.platform.ids import uuid7


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    name: Mapped[str]
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    email: Mapped[str | None]
    address: Mapped[str | None]
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    sku: Mapped[str]
    name: Mapped[str]
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    unit: Mapped[str] = mapped_column(default="each")
    unit_price: Mapped[Decimal] = mapped_column(default=Decimal(0))
    active: Mapped[bool] = mapped_column(default=True)


class PriceListEntry(Base):
    __tablename__ = "price_list"
    org_id: Mapped[uuid.UUID]
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), primary_key=True)
    unit_price: Mapped[Decimal]


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    number: Mapped[str | None]
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    customer_name_as_written: Mapped[str | None]
    order_date: Mapped[date | None]
    delivery_date: Mapped[date | None]
    status: Mapped[str] = mapped_column(default="approved")
    currency: Mapped[str]
    total: Mapped[Decimal] = mapped_column(default=Decimal(0))
    source_document_id: Mapped[uuid.UUID | None]
    approval_id: Mapped[uuid.UUID | None]
    created_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[uuid.UUID | None]
    description: Mapped[str]
    quantity: Mapped[Decimal]
    unit: Mapped[str] = mapped_column(default="each")
    unit_price: Mapped[Decimal]
    line_total: Mapped[Decimal]


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    number: Mapped[str]
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    customer_id: Mapped[uuid.UUID | None]
    issue_date: Mapped[date]
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(default="issued")
    currency: Mapped[str]
    subtotal: Mapped[Decimal]
    tax: Mapped[Decimal] = mapped_column(default=Decimal(0))
    total: Mapped[Decimal]
    approval_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    product_id: Mapped[uuid.UUID | None]
    description: Mapped[str]
    quantity: Mapped[Decimal]
    unit_price: Mapped[Decimal]
    line_total: Mapped[Decimal]


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    document_id: Mapped[uuid.UUID | None]
    status: Mapped[str] = mapped_column(default="running")
    pending_approval_id: Mapped[uuid.UUID | None]
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
