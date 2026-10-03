"""Customers, products and per-customer price lists. The price list, never the paper, is the record."""

import csv
import io
import uuid
from decimal import Decimal

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from keel.api.deps import Admin, Member, Viewer
from keel.audit.service import audit
from keel.domain.models import Customer, PriceListEntry, Product
from keel.identity.service import Ctx
from keel.platform.db import tenant_session
from keel.platform.errors import Conflict, NotFound

router = APIRouter(tags=["catalog"])


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = []
    email: str | None = None
    address: str | None = None
    payment_terms_days: int = Field(default=30, ge=0, le=365)


class CustomerOut(CustomerIn):
    id: str


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = []
    unit: str = "each"
    unit_price: Decimal = Field(ge=0, decimal_places=2)
    active: bool = True


class ProductOut(ProductIn):
    id: str


class PriceIn(BaseModel):
    product_id: uuid.UUID
    unit_price: Decimal = Field(ge=0, decimal_places=2)


class PriceOut(BaseModel):
    product_id: str
    sku: str
    name: str
    unit_price: Decimal


class ImportOut(BaseModel):
    created: int
    updated: int


def _customer_out(c: Customer) -> CustomerOut:
    return CustomerOut(
        id=str(c.id),
        name=c.name,
        aliases=c.aliases,
        email=c.email,
        address=c.address,
        payment_terms_days=c.payment_terms_days,
    )


def _product_out(p: Product) -> ProductOut:
    return ProductOut(
        id=str(p.id), sku=p.sku, name=p.name, aliases=p.aliases, unit=p.unit, unit_price=p.unit_price, active=p.active
    )


@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(ctx: Ctx = Viewer) -> list[CustomerOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        return [_customer_out(c) for c in (await db.scalars(select(Customer).order_by(Customer.name)))]


@router.post("/customers", response_model=CustomerOut)
async def create_customer(body: CustomerIn, ctx: Ctx = Member) -> CustomerOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        c = Customer(org_id=ctx.org_id, **body.model_dump())
        db.add(c)
        await audit(db, ctx.org_id, ctx.user_id, "customer.created", "customer", c.id, name=c.name)
    return _customer_out(c)


@router.put("/customers/{customer_id}", response_model=CustomerOut)
async def update_customer(customer_id: uuid.UUID, body: CustomerIn, ctx: Ctx = Member) -> CustomerOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        c = await db.get(Customer, customer_id)
        if c is None:
            raise NotFound("Customer not found.")
        for k, v in body.model_dump().items():
            setattr(c, k, v)
    return _customer_out(c)


@router.get("/products", response_model=list[ProductOut])
async def list_products(ctx: Ctx = Viewer) -> list[ProductOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        return [_product_out(p) for p in (await db.scalars(select(Product).order_by(Product.name)))]


@router.post("/products", response_model=ProductOut)
async def create_product(body: ProductIn, ctx: Ctx = Member) -> ProductOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        if await db.scalar(select(Product.id).where(Product.sku == body.sku)):
            raise Conflict(f"SKU {body.sku} already exists.")
        p = Product(org_id=ctx.org_id, **body.model_dump())
        db.add(p)
        await audit(db, ctx.org_id, ctx.user_id, "product.created", "product", p.id, sku=p.sku)
    return _product_out(p)


@router.put("/products/{product_id}", response_model=ProductOut)
async def update_product(product_id: uuid.UUID, body: ProductIn, ctx: Ctx = Member) -> ProductOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        p = await db.get(Product, product_id)
        if p is None:
            raise NotFound("Product not found.")
        for k, v in body.model_dump().items():
            setattr(p, k, v)
    return _product_out(p)


@router.post("/products/import", response_model=ImportOut)
async def import_products(file: UploadFile, ctx: Ctx = Admin) -> ImportOut:
    """CSV with columns: sku,name,unit,unit_price[,aliases separated by |]."""
    text = (await file.read()).decode("utf-8-sig")
    created = updated = 0
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        for row in csv.DictReader(io.StringIO(text)):
            sku = (row.get("sku") or "").strip()
            if not sku:
                continue
            fields = {
                "name": (row.get("name") or sku).strip(),
                "unit": (row.get("unit") or "each").strip(),
                "unit_price": Decimal((row.get("unit_price") or "0").strip()),
                "aliases": [a.strip() for a in (row.get("aliases") or "").split("|") if a.strip()],
            }
            existing = await db.scalar(select(Product).where(Product.sku == sku))
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(Product(org_id=ctx.org_id, sku=sku, **fields))
                created += 1
        await audit(db, ctx.org_id, ctx.user_id, "products.imported", None, None, created=created, updated=updated)
    return ImportOut(created=created, updated=updated)


@router.get("/customers/{customer_id}/prices", response_model=list[PriceOut])
async def customer_prices(customer_id: uuid.UUID, ctx: Ctx = Viewer) -> list[PriceOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        rows = await db.execute(
            select(PriceListEntry, Product)
            .join(Product, Product.id == PriceListEntry.product_id)
            .where(PriceListEntry.customer_id == customer_id)
        )
        return [PriceOut(product_id=str(p.id), sku=p.sku, name=p.name, unit_price=e.unit_price) for e, p in rows]


@router.put("/customers/{customer_id}/prices", response_model=list[PriceOut])
async def set_customer_price(customer_id: uuid.UUID, body: PriceIn, ctx: Ctx = Member) -> list[PriceOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        if await db.get(Customer, customer_id) is None or await db.get(Product, body.product_id) is None:
            raise NotFound("Customer or product not found.")
        entry = await db.get(PriceListEntry, (customer_id, body.product_id))
        if entry:
            entry.unit_price = body.unit_price
        else:
            db.add(
                PriceListEntry(
                    org_id=ctx.org_id, customer_id=customer_id, product_id=body.product_id, unit_price=body.unit_price
                )
            )
        await audit(
            db,
            ctx.org_id,
            ctx.user_id,
            "price.set",
            "customer",
            customer_id,
            product_id=str(body.product_id),
            unit_price=str(body.unit_price),
        )
    return await customer_prices(customer_id, ctx)
