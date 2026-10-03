"""Tier 4: Reducto Extract. Behind a flag; chosen per document type by the bake-off, never by default.

Request and response shapes follow Reducto's public API (upload, then extract with a JSON schema). They
live only in `_request` and `_parse`; confirm them against the live API with free credits before relying
on results. Reducto is rate-limited (about 1 request/s), so it runs only on pages that failed validation.
"""

from typing import Any

import httpx
from pydantic import BaseModel

from keel.documents.engines.base import EngineResult, PageInput
from keel.documents.engines.plain import pages_pdf, plain_schema, typed
from keel.platform.config import get_settings

INSTRUCTIONS = (
    "Transcribe only what is written. Never invent, round or correct a value. "
    "If a field is missing or unreadable, return null. A blank is not zero."
)


class ReductoExtractor:
    name = "reducto"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        if not s.reducto_api_key:
            raise RuntimeError("REDUCTO_API_KEY is not set.")
        self.base, self.price, self.conf = s.reducto_url.rstrip("/"), s.reducto_usd_per_page, s.tier4_confidence
        self.client = client or httpx.AsyncClient(timeout=120)
        self.headers = {"Authorization": f"Bearer {s.reducto_api_key}"}

    def _request(self, file_id: str, schema: type[BaseModel]) -> dict[str, Any]:
        return {"input": file_id, "instructions": {"schema": plain_schema(schema), "system_prompt": INSTRUCTIONS}}

    @staticmethod
    def _parse(body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        result = body.get("result")
        data = result[0] if isinstance(result, list) and result else result
        pages = int((body.get("usage") or {}).get("num_pages", 0))
        return (data if isinstance(data, dict) else {}), pages

    async def extract(self, pages: list[PageInput], schema: type[BaseModel], hint: str = "") -> EngineResult:
        up = await self.client.post(
            f"{self.base}/upload",
            headers=self.headers,
            files={"file": ("doc.pdf", pages_pdf(pages), "application/pdf")},
        )
        up.raise_for_status()
        r = await self.client.post(
            f"{self.base}/extract", headers=self.headers, json=self._request(up.json()["file_id"], schema)
        )
        r.raise_for_status()
        data, billed = self._parse(r.json())
        billed = billed or len(pages)
        return EngineResult(
            data=typed(schema, data, self.conf), engine=self.name, model="reducto-extract", cost_usd=billed * self.price
        )
