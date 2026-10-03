"""Match what is written on paper to the tenant's customers, products and price lists.

Matching proposes; it never silently guesses. Below the threshold, the result is "unmatched" and the
review screen asks the owner. Prices always come from the price list or catalog, never the paper.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keel.domain.models import Customer, PriceListEntry, Product

THRESHOLD = 80


@dataclass
class Match:
    id: uuid.UUID | None
    name: str | None
    score: float


def _best(written: str | None, options: dict[str, uuid.UUID]) -> Match:
    if not written or not options:
        return Match(None, None, 0.0)
    hit = process.extractOne(written.lower(), list(options), scorer=fuzz.WRatio)
    if hit is None or hit[1] < THRESHOLD:
        return Match(None, None, float(hit[1]) if hit else 0.0)
    return Match(options[hit[0]], hit[0], float(hit[1]))


async def match_customer(db: AsyncSession, written: str | None) -> Match:
    options: dict[str, uuid.UUID] = {}
    names: dict[uuid.UUID, str] = {}
    for c in await db.scalars(select(Customer)):
        names[c.id] = c.name
        for n in [c.name, *c.aliases]:
            options[n.lower()] = c.id
    m = _best(written, options)
    return Match(m.id, names.get(m.id) if m.id else None, m.score)


async def catalog(db: AsyncSession) -> tuple[dict[str, uuid.UUID], dict[uuid.UUID, Product]]:
    options: dict[str, uuid.UUID] = {}
    products: dict[uuid.UUID, Product] = {}
    for p in await db.scalars(select(Product).where(Product.active.is_(True))):
        products[p.id] = p
        for n in [p.name, p.sku, *p.aliases]:
            options[n.lower()] = p.id
    return options, products


def match_product(written: str | None, options: dict[str, uuid.UUID],
                  products: dict[uuid.UUID, Product]) -> Match:
    m = _best(written, options)
    return Match(m.id, products[m.id].name if m.id else None, m.score)


async def price_for(db: AsyncSession, customer_id: uuid.UUID | None, product: Product) -> tuple[Decimal, str]:
    if customer_id:
        entry = await db.get(PriceListEntry, (customer_id, product.id))
        if entry:
            return entry.unit_price, "customer_price_list"
    return product.unit_price, "catalog"
