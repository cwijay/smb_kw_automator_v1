import re
from decimal import Decimal
from typing import ClassVar

import httpx
import pytest

from keel.search import hybrid
from keel.search.embed import Embedded
from tests.fixtures import haccp_log_pdf, order_sheet_pdf
from tests.integration.test_production import _upload


async def _q(c: httpx.AsyncClient, q: str) -> list[dict]:  # type: ignore[type-arg]
    r = await c.get("/api/search", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_search_by_words_and_by_spelling(owner: httpx.AsyncClient) -> None:
    await _upload(owner, order_sheet_pdf(["11 Malai Kulfi 4.50 49.50"], customer="Saffron Grill"), "order_pad", "o.pdf")
    await _upload(owner, haccp_log_pdf(["Pasteurization temperature 162 F 08:40 RP"]), "haccp_log", "h.pdf")

    exact = await _q(owner, "pasteurization")
    assert exact[0]["file"] == "h.pdf" and exact[0]["page"] == 1
    assert "words" in exact[0]["matched"] and "<b>" in exact[0]["snippet"]

    # full-text misses a misspelled name; trigram word similarity still finds the paper
    typo = await _q(owner, "safron gril")
    assert typo[0]["file"] == "o.pdf" and typo[0]["matched"] == ["spelling"]
    assert "<b>Saffron</b>" in typo[0]["snippet"] or "<b>Grill</b>" in typo[0]["snippet"]

    assert await _q(owner, "xylophone quartz") == []


class ConceptEmbedder:
    """Test stand-in for a real embedding model: words about the same thing land on the same axis."""

    name = "test-concepts"
    CONCEPTS: ClassVar[list[set[str]]] = [{"kulfi", "dessert", "frozen", "ice"}, {"temperature", "probe", "heat"}]

    async def embed(self, texts: list[str]) -> Embedded:
        vectors = []
        for t in texts:
            words = set(re.findall(r"[a-z]+", t.lower()))
            v = [0.0] * 512
            for i, concept in enumerate(self.CONCEPTS):
                v[i] = float(len(words & concept))
            v[511] = 0.1  # never a zero vector
            vectors.append(v)
        return Embedded(vectors, self.name, 0, Decimal(0))


async def test_search_by_meaning_with_an_embedding_model(
    owner: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hybrid, "embedder", lambda: ConceptEmbedder())
    await _upload(owner, order_sheet_pdf(["3 Mango Kulfi 5.50 16.50"], customer="Rasoi Kitchen"), "order_pad", "m.pdf")
    hits = await _q(owner, "frozen dessert")
    assert hits[0]["file"] == "m.pdf" and hits[0]["matched"] == ["meaning"]


async def test_search_is_tenant_scoped(owner: httpx.AsyncClient, other_tenant: httpx.AsyncClient) -> None:
    await _upload(owner, order_sheet_pdf(["2 Mango Kulfi 5.50 11.00"], customer="Golden Spoon"), "order_pad", "g.pdf")
    assert await _q(owner, "golden spoon")
    assert await _q(other_tenant, "golden spoon") == []
    assert await _q(other_tenant, "goldn spon") == []
