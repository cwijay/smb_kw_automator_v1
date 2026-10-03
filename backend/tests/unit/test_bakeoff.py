from pathlib import Path

import pytest
from pydantic import BaseModel

from keel.documents.engines.base import EngineResult, PageInput
from keel.documents.engines.fake import FakeExtractor
from keel.evals import parsers
from keel.evals.parsers import bakeoff, compare
from keel.evals.synthetic import write


def test_compare_outcomes() -> None:
    got = {
        "a": {"value": "11.000", "status": "read"},
        "b": {"value": "Rasoi", "status": "read"},
        "c": {"value": None, "status": "unreadable"},
        "d": {"value": "0", "status": "read"},
    }
    out = {p: o for p, _, _, o in compare({"a": "11", "b": "rasoi ", "c": None, "d": None, "e": "x"}, got)}
    assert out == {"a": "correct", "b": "correct", "c": "empty_ok", "d": "invented", "e": "wrong"}


class Blank:
    name = "blank"

    async def extract(self, pages: list[PageInput], schema: type[BaseModel], hint: str = "") -> EngineResult:
        return EngineResult(
            data=schema.model_validate({}) if not schema.model_fields else _empty(schema), engine="blank"
        )


class ZeroFiller(FakeExtractor):
    """Reads like the local engine, then 'helpfully' turns every empty number into 0."""

    async def extract(self, pages: list[PageInput], schema: type[BaseModel], hint: str = "") -> EngineResult:
        r = await super().extract(pages, schema, hint)
        data = r.data.model_dump()
        for reading in data.get("readings", []):
            if reading["value"]["value"] is None:
                reading["value"] = {"value": "0", "status": "read", "confidence": 0.9}
        return EngineResult(data=schema.model_validate(data), engine="zero")


def _empty(schema: type[BaseModel]) -> BaseModel:
    required = {n: {} for n, f in schema.model_fields.items() if f.is_required()}
    return schema.model_validate(required)


def test_bakeoff_catches_bad_engines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gold = tmp_path / "gold"
    write(gold)
    engines = {"local-rules": FakeExtractor(), "blank": Blank(), "zero": ZeroFiller()}
    monkeypatch.setattr(parsers, "engine", lambda name: engines[name])
    monkeypatch.setattr(parsers, "available", lambda name: name in engines)
    totals = bakeoff(["local-rules", "blank", "zero", "ade"], gold, tmp_path / "out")
    assert totals["local-rules"].accuracy == 1.0 and totals["local-rules"].invented == 0
    assert totals["blank"].accuracy == 0.0 and totals["blank"].invented == 0
    assert totals["zero"].invented == 1  # the blank HACCP reading, filled with 0
    report = (tmp_path / "out" / "report.md").read_text()
    assert "Skipped (no API key configured): ade" in report and "| zero |" in report
    assert (tmp_path / "out" / "results.csv").read_text().count("invented") == 1
