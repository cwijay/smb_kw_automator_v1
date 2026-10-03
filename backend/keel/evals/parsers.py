"""Parser bake-off: `keel evals parsers --engines local-rules,luna,gemini,sol,reducto,ade --gold <dir>`.

For every engine and gold document: render, OCR when there is no text layer, extract, then compare each
expected field. Reports field accuracy, invented values (a value where the paper is empty: the number
that matters most), unreadable recall, $ per 1k pages and p50/p95 latency, by engine, document type and
field. Writes results.csv and report.md. Engines without keys are skipped and listed as such.
"""

import asyncio
import csv
import json
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from keel.documents import ocr
from keel.documents.engines.base import PageInput
from keel.documents.engines.registry import available, engine
from keel.documents.pipeline import flatten
from keel.documents.render import page_text, render
from keel.documents.schemas import SCHEMAS


@dataclass
class Tally:
    correct: int = 0
    wrong: int = 0
    invented: int = 0
    empty_ok: int = 0
    empty_total: int = 0
    pages: int = 0
    cost: float = 0.0
    latencies: list[float] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        n = self.correct + self.wrong
        return self.correct / n if n else 1.0

    @property
    def unreadable_recall(self) -> float:
        return self.empty_ok / self.empty_total if self.empty_total else 1.0

    def p(self, q: float) -> float:
        if not self.latencies:
            return 0.0
        xs = sorted(self.latencies)
        return xs[min(len(xs) - 1, int(q * len(xs)))]


def _norm(v: Any) -> Any:
    if v is None:
        return None
    s = str(v).strip()
    try:
        return Decimal(s.replace(",", "").replace("$", ""))
    except InvalidOperation:
        return re.sub(r"\s+", " ", s).casefold()


def _inputs(data: bytes, mime: str) -> list[PageInput]:
    out = []
    for rp in render(data, mime):
        words = rp.words if rp.has_text_layer else ocr.ocr_words(rp.png)
        out.append(PageInput(png=rp.png, text=page_text(words), words=words))
    return out


def compare(expected: dict[str, Any], got: dict[str, dict[str, Any]]) -> list[tuple[str, Any, Any, str]]:
    rows = []
    for path, exp in expected.items():
        g = got.get(path) or {}
        value = g.get("value") if g.get("status") == "read" else None
        if exp is None:
            outcome = "invented" if value is not None else "empty_ok"
        else:
            outcome = "correct" if value is not None and _norm(value) == _norm(exp) else "wrong"
        rows.append((path, exp, value, outcome))
    return rows


@dataclass
class Results:
    totals: dict[str, Tally]
    by_kind: dict[tuple[str, str], Tally]
    by_field: dict[tuple[str, str], list[int]]
    rows: list[list[Any]]
    skipped: list[str]


async def score(engines: list[str], docs: list[dict[str, Any]], inputs: dict[str, list[PageInput]]) -> Results:
    r = Results({}, defaultdict(Tally), defaultdict(lambda: [0, 0]), [], [e for e in engines if not available(e)])
    for name in [e for e in engines if available(e)]:
        ex, t = engine(name), Tally()
        for d in docs:
            pages = inputs[d["file"]]
            started = time.perf_counter()
            result = await ex.extract(pages, SCHEMAS[d["kind"]])
            elapsed = time.perf_counter() - started
            kind_t = r.by_kind[(name, d["kind"])]
            for tally in (t, kind_t):
                tally.pages += len(pages)
                tally.cost += result.cost_usd
                tally.latencies.append(elapsed)
            for path, exp, value, outcome in compare(d["expected"], dict(flatten(result.data))):
                r.rows.append([name, d["file"], d["kind"], path, exp, value, outcome])
                for tally in (t, kind_t):
                    tally.correct += outcome == "correct"
                    tally.wrong += outcome == "wrong"
                    tally.invented += outcome == "invented"
                    tally.empty_ok += outcome == "empty_ok"
                    tally.empty_total += exp is None
                key = (name, f"{d['kind']}.{re.sub(r'\[\d+\]', '[]', path)}")
                r.by_field[key][0] += outcome in ("wrong", "invented")
                r.by_field[key][1] += 1
        r.totals[name] = t
    return r


def bakeoff(engines: list[str], gold: Path, out: Path) -> dict[str, Tally]:
    docs = [json.loads(p.read_text()) for p in sorted(gold.glob("*.json"))]
    if not docs:
        raise SystemExit(f"No gold documents (*.json) in {gold}")
    inputs = {d["file"]: _inputs((gold / d["file"]).read_bytes(), d["mime"]) for d in docs}
    r = asyncio.run(score(engines, docs, inputs))
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["engine", "file", "kind", "field", "expected", "got", "outcome"])
        w.writerows(r.rows)
    (out / "report.md").write_text(_report(gold, r))
    return r.totals


def _row(name: str, t: Tally) -> str:
    per_k = t.cost / t.pages * 1000 if t.pages else 0.0
    return (
        f"| {name} | {t.accuracy:.1%} | {t.invented} | {t.unreadable_recall:.0%} | ${per_k:.2f} "
        f"| {statistics.median(t.latencies) if t.latencies else 0:.2f}s | {t.p(0.95):.2f}s |"
    )


HEAD = (
    "| engine | field accuracy | invented values | unreadable recall | $ / 1k pages | p50 | p95 |\n"
    "|---|---|---|---|---|---|---|"
)


def _report(gold: Path, r: Results) -> str:
    totals, by_kind, by_field, skipped, head = r.totals, r.by_kind, r.by_field, r.skipped, HEAD
    lines = [f"# Parser bake-off\n\nGold set: `{gold}`\n", "## Overall\n", head]
    lines += [_row(n, t) for n, t in totals.items()]
    if skipped:
        lines.append(f"\nSkipped (no API key configured): {', '.join(skipped)}")
    lines += ["\n## By document type\n", head.replace("| engine |", "| engine · type |", 1)]
    lines += [_row(f"{n} · {k}", t) for (n, k), t in sorted(by_kind.items())]
    lines.append("\n## Fields with errors\n\n| engine | field | errors / seen |\n|---|---|---|")
    worst = sorted(((n, f, e, s) for (n, f), (e, s) in by_field.items() if e), key=lambda x: -x[2])
    lines += [f"| {n} | `{f}` | {e} / {s} |" for n, f, e, s in worst[:30]] or ["| — | none | — |"]
    lines.append("\n*Invented values* counts fields that are empty on the paper but came back with a value.\n")
    return "\n".join(lines)
