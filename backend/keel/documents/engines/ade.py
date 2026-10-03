"""Tier 4: LandingAI Agentic Document Extraction (ADE). Behind a flag; chosen by the bake-off.

Two calls, following ADE's public API: parse the document to markdown, then extract against a JSON
schema. Shapes live only in `_parse_markdown` and `_extraction`; confirm them against the live API
with free credits before relying on results.
"""

import json
from typing import Any

import httpx
from pydantic import BaseModel

from keel.documents.engines.base import EngineResult, PageInput
from keel.documents.engines.plain import pages_pdf, plain_schema, typed
from keel.platform.config import get_settings


class AdeExtractor:
    name = "ade"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        if not s.landingai_api_key:
            raise RuntimeError("VISION_AGENT_API_KEY is not set.")
        self.base, self.price, self.conf = s.ade_url.rstrip("/"), s.ade_usd_per_page, s.tier4_confidence
        self.client = client or httpx.AsyncClient(timeout=180)
        self.headers = {"Authorization": f"Bearer {s.landingai_api_key}"}

    @staticmethod
    def _parse_markdown(body: dict[str, Any]) -> tuple[str, int]:
        pages = int((body.get("metadata") or {}).get("page_count", 0))
        return str(body.get("markdown") or ""), pages

    @staticmethod
    def _extraction(body: dict[str, Any]) -> dict[str, Any]:
        data = body.get("extraction")
        return data if isinstance(data, dict) else {}

    async def extract(self, pages: list[PageInput], schema: type[BaseModel], hint: str = "") -> EngineResult:
        parsed = await self.client.post(
            f"{self.base}/v1/ade/parse",
            headers=self.headers,
            files={"document": ("doc.pdf", pages_pdf(pages), "application/pdf")},
        )
        parsed.raise_for_status()
        markdown, billed = self._parse_markdown(parsed.json())
        r = await self.client.post(
            f"{self.base}/v1/ade/extract",
            headers=self.headers,
            files={"markdown": ("doc.md", markdown.encode(), "text/markdown")},
            data={"schema": json.dumps(plain_schema(schema))},
        )
        r.raise_for_status()
        billed = billed or len(pages)
        return EngineResult(
            data=typed(schema, self._extraction(r.json()), self.conf),
            engine=self.name,
            model="ade-dpt",
            cost_usd=billed * self.price,
        )
