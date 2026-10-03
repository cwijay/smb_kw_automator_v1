"""Every extraction engine by name, for the pipeline's tiers and the parser bake-off."""

from keel.documents.engines.base import Extractor
from keel.platform.config import get_settings

ENGINES = ("local-rules", "luna", "gemini", "sol", "reducto", "ade")


def engine(name: str) -> Extractor:
    s = get_settings()
    if name == "local-rules":
        from keel.documents.engines.fake import FakeExtractor

        return FakeExtractor()
    if name in ("luna", "gemini", "sol"):
        from keel.documents.engines.llm import LlmExtractor

        model = {"luna": s.model_default, "gemini": s.model_vision_handwriting, "sol": s.model_tier4_sol}[name]
        return LlmExtractor(model)
    if name == "reducto":
        from keel.documents.engines.reducto import ReductoExtractor

        return ReductoExtractor()
    if name == "ade":
        from keel.documents.engines.ade import AdeExtractor

        return AdeExtractor()
    raise ValueError(f"Unknown engine {name!r}. Known: {', '.join(ENGINES)}")


def available(name: str) -> bool:
    """Whether the keys an engine needs are configured (local-rules always is)."""
    s = get_settings()
    return {
        "local-rules": True,
        "luna": bool(s.openai_api_key),
        "sol": bool(s.openai_api_key),
        "gemini": bool(s.google_api_key),
        "reducto": bool(s.reducto_api_key),
        "ade": bool(s.landingai_api_key),
    }.get(name, False)
