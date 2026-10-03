import pytest

from keel.platform import tracing
from keel.platform.config import get_settings


def test_tracing_is_off_without_keys() -> None:
    tracing._handler.cache_clear()
    assert tracing.trace_config("ask-keel") == {}


def test_tracing_tags_tenant_without_personal_data(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = object()
    monkeypatch.setattr(tracing, "_handler", lambda: handler)
    cfg = tracing.trace_config("ask-keel", org_id=None, user_id=None, session="conv-1")
    assert cfg["callbacks"] == [handler] and cfg["metadata"]["langfuse_session_id"] == "conv-1"
    assert get_settings().langfuse_public_key is None
