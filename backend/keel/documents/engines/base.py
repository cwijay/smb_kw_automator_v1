"""Provider-agnostic extraction interface. Every engine returns the same shape plus cost."""

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


@dataclass
class PageInput:
    png: bytes
    text: str  # reading-order text from the text layer or OCR
    words: list[dict[str, Any]]


@dataclass
class EngineResult:
    data: BaseModel
    engine: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class Extractor(Protocol):
    name: str

    async def extract(self, pages: list[PageInput], schema: type[BaseModel], hint: str = "") -> EngineResult: ...


# USD per 1M tokens (input, output). Kept in one place; update when providers change prices.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-6-luna": (0.10, 0.50),
    "gemini-3.8-flash": (0.75, 3.75),
    "gpt-6-sol": (2.00, 10.00),
    "accounts/fireworks/models/glm-5p3": (1.40, 4.40),
}


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
