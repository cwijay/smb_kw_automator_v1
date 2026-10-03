"""Demo tenant for local runs: `keel seed`. Synthetic data only, no real customer documents."""

import uuid
from decimal import Decimal

from sqlalchemy import select

from keel.documents.render import render
from keel.domain.models import Customer, PriceListEntry, Product
from keel.identity import service
from keel.identity.models import User
from keel.platform.db import global_session, tenant_session

DEMO_EMAIL = "owner@demo.keel"
DEMO_PASSWORD = "keel-demo-2026"

CUSTOMERS = [
    ("Rasoi Kitchen", ["Rasoi", "Rasoi III"], 30),
    ("Saffron Grill", ["Saffron"], 14),
    ("Little Bombay Cafe", ["L Bombay", "LBC"], 30),
]
PRODUCTS = [
    ("MK-TUB", "Malai Kulfi", "tub", "5.00", ["malai"]),
    ("MG-TUB", "Mango Kulfi", "tub", "5.50", ["mango"]),
    ("PS-TUB", "Pista Kulfi", "tub", "5.75", ["pista", "kesar pista"]),
    ("PM-TUB", "Paan Masala", "tub", "6.00", ["paan"]),
    ("RP-TUB", "Rose Petal Kulfi", "tub", "5.50", ["rose"]),
    ("FW-TUB", "Figs & Walnut Kulfi", "tub", "6.25", ["figs walnut"]),
]


def _sheet(customer: str, number: str, lines: list[str], total: str | None = None) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A5")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    rows = [
        f"Customer: {customer}",
        f"Order #: {number}",
        "Date: 2026-10-01",
        "Deliver: 2026-10-04",
        "Qty Item Price Amount",
        *lines,
    ] + ([f"Total: {total}"] if total else [])
    for row in rows:
        pdf.cell(0, 8, row, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


async def seed() -> None:
    async with global_session() as db:
        exists = await db.scalar(select(User.id).where(User.email == DEMO_EMAIL))
    if not exists:
        await service.signup(org_name="Demo Kulfi Co", name="Demo Owner", email=DEMO_EMAIL, password=DEMO_PASSWORD)
    async with global_session() as db:
        user = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
    assert user is not None
    orgs = await service._memberships(user.id)
    org_id = orgs[0][1].id
    async with tenant_session(org_id, user.id) as db:
        if not await db.scalar(select(Product.id).limit(1)):
            products = {}
            for sku, name, unit, price, aliases in PRODUCTS:
                p = Product(org_id=org_id, sku=sku, name=name, unit=unit, unit_price=Decimal(price), aliases=aliases)
                db.add(p)
                products[sku] = p
            for name, aliases, terms in CUSTOMERS:
                c = Customer(
                    org_id=org_id,
                    name=name,
                    aliases=aliases,
                    payment_terms_days=terms,
                    email=f"orders@{name.split()[0].lower()}.example",
                )
                db.add(c)
                if name == "Rasoi Kitchen":
                    await db.flush()
                    db.add(
                        PriceListEntry(
                            org_id=org_id,
                            customer_id=c.id,
                            product_id=products["MK-TUB"].id,
                            unit_price=Decimal("4.50"),
                        )
                    )
    samples = [
        (
            "rasoi-order-1001.pdf",
            "application/pdf",
            _sheet(
                "Rasoi III",
                "1001",
                [
                    "11 Malai Kulfi 4.50 49.50",
                    "3 Mango Kulfi 5.50 16.50",
                    "~2 Chocolate (crossed out)",
                    "1 Paan Masala 6.00 6.00",
                ],
                "72.00",
            ),
        ),
        (
            "saffron-photo.png",
            "image/png",
            render(
                _sheet("Saffron Grill", "1002", ["6 Pista Kulfi 5.75 34.50", "4 Rose Petal 5.50 22.00"], "56.50"),
                "application/pdf",
            )[0].png,
        ),
        (
            "unknown-customer.pdf",
            "application/pdf",
            _sheet("Golden Spoon", "1003", ["2 Figs Walnut 6.25 12.50"], "12.50"),
        ),
    ]
    await _upload_samples(org_id, user.id, samples)
    print(f"Demo tenant ready. Sign in as {DEMO_EMAIL} / {DEMO_PASSWORD}")


async def _upload_samples(org_id: uuid.UUID, user_id: uuid.UUID, samples: list[tuple[str, str, bytes]]) -> None:
    import hashlib

    from keel.documents.models import Document
    from keel.files.storage import doc_key, storage
    from keel.platform.ids import uuid7
    from keel.workers.runner import drain, enqueue

    async with tenant_session(org_id, user_id) as db:
        for name, mime, data in samples:
            digest = hashlib.sha256(data).hexdigest()
            if await db.scalar(select(Document.id).where(Document.sha256 == digest)):
                continue
            doc_id = uuid7()
            key = doc_key(org_id, doc_id, f"original-{name}")
            await storage().put(key, data)
            db.add(
                Document(
                    id=doc_id,
                    org_id=org_id,
                    kind="order_pad",
                    filename=name,
                    mime=mime,
                    size_bytes=len(data),
                    sha256=digest,
                    storage_key=key,
                    source="camera" if mime.startswith("image") else "upload",
                    created_by=user_id,
                )
            )
            await db.flush()
            await enqueue(db, org_id, "process_document", document_id=str(doc_id), user_id=str(user_id))
    await drain()
