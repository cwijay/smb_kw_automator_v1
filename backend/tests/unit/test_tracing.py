from typing import Any

import pytest

from keel.platform import tracing
from keel.platform.config import get_settings


@pytest.fixture(autouse=True)
def fresh(monkeypatch: pytest.MonkeyPatch) -> Any:
    tracing._handler.cache_clear()
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    tracing._handler.cache_clear()
    get_settings.cache_clear()


def test_tracing_is_off_without_keys() -> None:
    assert tracing.trace_config("ask-keel") == {}


def test_keys_without_a_base_url_never_fall_back_to_the_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    assert tracing.trace_config("ask-keel") == {}


def test_client_is_built_from_keel_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import langfuse
    import langfuse.langchain

    built: dict[str, Any] = {}
    monkeypatch.setattr(langfuse, "Langfuse", lambda **kw: built.update(kw))
    monkeypatch.setattr(langfuse.langchain, "CallbackHandler", lambda public_key: ("handler", public_key))
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3001")
    cfg = tracing.trace_config("ask-keel", session="conv-1")
    assert built == {"public_key": "pk-lf-x", "secret_key": "sk-lf-x", "base_url": "http://localhost:3001"}
    assert cfg["callbacks"] == [("handler", "pk-lf-x")] and cfg["metadata"]["langfuse_session_id"] == "conv-1"
