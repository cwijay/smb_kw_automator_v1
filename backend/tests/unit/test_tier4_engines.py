"""Contract tests for tier-4 adapters, on recorded-shaped responses. No network."""

import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest

from keel.documents.engines.ade import AdeExtractor
from keel.documents.engines.base import PageInput
from keel.documents.engines.plain import plain_schema, typed
from keel.documents.engines.reducto import ReductoExtractor
from keel.documents.render import render
from keel.documents.schemas import BatchSheetX, HaccpLogX
from keel.platform.config import get_settings
from tests.fixtures import batch_sheet_pdf

BATCH = {
    "product_name": "Malai Kulfi",
    "batch_number": "B-001",
    "made_on": "2026-10-01",
    "output_lot": "L-1042",
    "quantity": 120,
    "unit": "tub",
    "prepared_by": None,
    "ingredients": [
        {"ingredient": "Whole Milk", "lot_code": "M-0129", "quantity": "136", "unit": "lbs"},
        {"ingredient": "Rose Water", "lot_code": None, "quantity": "about 140", "unit": "ml"},
    ],
}


@pytest.fixture
def pages() -> list[PageInput]:
    rp = render(batch_sheet_pdf(["Whole Milk M-0129 136 lbs"]), "application/pdf")[0]
    return [PageInput(png=rp.png, text="", words=[])]


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REDUCTO_API_KEY", "test-reducto")
    monkeypatch.setenv("VISION_AGENT_API_KEY", "test-ade")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()  # later tests must not see the fake keys


def test_plain_schema_is_nullable_and_nested() -> None:
    s = plain_schema(BatchSheetX)
    assert s["properties"]["quantity"]["type"] == ["number", "null"]
    assert s["properties"]["ingredients"]["items"]["properties"]["lot_code"]["type"] == ["string", "null"]
    assert "Blank stays blank" in s["properties"]["ingredients"]["items"]["properties"]["lot_code"]["description"]
    assert plain_schema(HaccpLogX)["properties"]["readings"]["type"] == "array"


def test_typed_never_turns_missing_into_zero() -> None:
    x = typed(BatchSheetX, BATCH, 0.85)
    assert isinstance(x, BatchSheetX)
    assert x.quantity.value == Decimal(120) and x.quantity.status == "read" and x.quantity.confidence == 0.85
    assert x.prepared_by.status == "unreadable" and x.prepared_by.value is None
    rose = x.ingredients[1]
    assert rose.lot_code.status == "unreadable"  # null from a service is reviewed, never "blank"
    assert rose.quantity.status == "unreadable" and rose.quantity.value is None  # "about 140" is not a number


def _transport(log: list[httpx.Request], routes: dict[str, dict[str, Any]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        for suffix, body in routes.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_reducto_contract(pages: list[PageInput]) -> None:
    log: list[httpx.Request] = []
    routes = {"/upload": {"file_id": "reducto://abc"}, "/extract": {"result": [BATCH], "usage": {"num_pages": 1}}}
    ex = ReductoExtractor(client=httpx.AsyncClient(transport=_transport(log, routes)))
    out = await ex.extract(pages, BatchSheetX)
    assert [r.url.path for r in log] == ["/upload", "/extract"]
    assert all(r.headers["authorization"] == "Bearer test-reducto" for r in log)
    sent = json.loads(log[1].content)
    assert sent["input"] == "reducto://abc" and sent["instructions"]["schema"]["properties"]["output_lot"]
    assert isinstance(out.data, BatchSheetX) and out.data.output_lot.value == "L-1042"
    assert out.engine == "reducto" and out.cost_usd == pytest.approx(get_settings().reducto_usd_per_page)


async def test_ade_contract(pages: list[PageInput]) -> None:
    log: list[httpx.Request] = []
    routes = {
        "/v1/ade/parse": {"markdown": "# Batch Sheet\nProduct: Malai Kulfi", "metadata": {"page_count": 1}},
        "/v1/ade/extract": {"extraction": BATCH, "extraction_metadata": {}},
    }
    ex = AdeExtractor(client=httpx.AsyncClient(transport=_transport(log, routes)))
    out = await ex.extract(pages, BatchSheetX)
    assert [r.url.path for r in log] == ["/v1/ade/parse", "/v1/ade/extract"]
    assert b"Malai Kulfi" in log[1].content and b'"output_lot"' in log[1].content  # markdown + schema sent
    assert isinstance(out.data, BatchSheetX) and out.data.ingredients[0].lot_code.value == "M-0129"


async def test_adapters_refuse_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDUCTO_API_KEY")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="REDUCTO_API_KEY"):
        ReductoExtractor()
