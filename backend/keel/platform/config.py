"""Runtime configuration. Every tunable (model IDs, thresholds, limits) lives here, never in code."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KEEL_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"

    # Runtime connects as a role WITHOUT BYPASSRLS; migrations run as the owner role.
    database_url: str = "postgresql+psycopg://keel_app:keel_app@localhost:5432/keel"
    database_owner_url: str = "postgresql+psycopg://keel_owner:keel_owner@localhost:5432/keel"

    storage_dir: Path = Path("./var/storage")
    frontend_url: str = "http://localhost:3000"

    session_cookie: str = "keel_session"
    session_ttl_days: int = 30
    cookie_secure: bool = False
    magic_link_ttl_minutes: int = 20
    invite_ttl_days: int = 7

    # "fake" runs a deterministic local extractor and agent (no API keys, used by tests/demo).
    # "live" calls the model providers. "auto" picks live when OPENAI_API_KEY is set.
    llm_mode: Literal["auto", "fake", "live"] = "auto"
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    fireworks_api_key: str | None = Field(default=None, validation_alias="FIREWORKS_API_KEY")

    model_default: str = "openai:gpt-6-luna"
    model_vision_handwriting: str = "google_genai:gemini-3.8-flash"
    model_reasoning: str = "fireworks:accounts/fireworks/models/glm-5p3"
    model_fallback: str = "openai:gpt-6-luna"

    # Tier 4: only for pages that still fail checks after the Gemini re-read. Off unless named here;
    # which one is decided per document type by `keel evals parsers`.
    tier4_engine: Literal["reducto", "ade", "sol"] | None = None
    tier4_confidence: float = 0.85  # services return no per-field confidence; this is what we assume
    model_tier4_sol: str = "openai:gpt-6-sol"
    reducto_api_key: str | None = Field(default=None, validation_alias="REDUCTO_API_KEY")
    reducto_url: str = "https://platform.reducto.ai"
    reducto_usd_per_page: float = 0.02  # placeholder: set from your plan; bake-off cost figures use it
    landingai_api_key: str | None = Field(default=None, validation_alias="VISION_AGENT_API_KEY")
    ade_url: str = "https://api.va.landing.ai"
    ade_usd_per_page: float = 0.03  # placeholder: set from your plan

    # Search: full-text + pg_trgm spelling + (live only) OpenAI embeddings, fused by RRF.
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 512
    embedding_usd_per_mtok: Decimal = Decimal("0.02")
    chunk_chars: int = 600
    rrf_k: int = 60
    search_pool: int = 20
    search_min_similarity: float = 0.25  # cosine floor for "similar meaning"
    search_fuzzy: float = 0.5  # pg_trgm word_similarity floor for "close spelling"

    ocr_enabled: bool = True
    max_upload_mb: int = 25
    low_confidence: float = 0.75
    unusual_quantity_factor: float = 3.0
    worker_poll_seconds: float = 1.0
    monthly_ai_budget_usd: float = 10.0

    @property
    def live_llm(self) -> bool:
        if self.llm_mode == "fake":
            return False
        if self.llm_mode == "live":
            return True
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
