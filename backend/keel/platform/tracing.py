"""Optional LLM tracing with Langfuse (self-hostable). Off unless LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and
LANGFUSE_SECRET_KEY are all set and the `observability` extra is installed. Traces contain document text, so
point it at a Langfuse you control. Traces carry org and user ids, never names or emails.

The client is built from Keel's settings (environment or backend/.env), never from the SDK's own environment
lookup: that lookup ignores backend/.env and silently defaults to Langfuse Cloud. Without an explicit base
URL, tracing stays off.
"""

import uuid
from functools import lru_cache
from typing import Any

from keel.platform.config import get_settings
from keel.platform.logging import log


@lru_cache
def _handler() -> Any | None:
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    if not s.langfuse_base_url:
        log.warning("tracing.disabled", reason="LANGFUSE_BASE_URL is not set; refusing to default to Langfuse Cloud")
        return None
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler
    except ImportError:
        log.warning("tracing.disabled", reason="langfuse keys set but the observability extra is not installed")
        return None
    # Registers the client for this public key; the handler below uses that client, not the SDK's env lookup.
    Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, base_url=s.langfuse_base_url)
    return CallbackHandler(public_key=s.langfuse_public_key)


def trace_config(
    name: str, org_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None, session: str | None = None
) -> dict[str, Any]:
    """RunnableConfig fragment to merge into a LangChain/LangGraph call. Empty when tracing is off."""
    handler = _handler()
    if handler is None:
        return {}
    metadata: dict[str, Any] = {"langfuse_tags": [name]}
    if org_id:
        metadata["langfuse_tags"].append(f"org:{org_id}")
    if user_id:
        metadata["langfuse_user_id"] = str(user_id)
    if session:
        metadata["langfuse_session_id"] = session
    return {"callbacks": [handler], "metadata": metadata, "run_name": name}
