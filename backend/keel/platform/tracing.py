"""Optional LLM tracing with Langfuse (self-hostable). Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY
are set and the `observability` extra is installed. Traces contain document text, so point it at a
Langfuse you control. Traces carry org and user ids, never names or emails.
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
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        log.warning("tracing.disabled", reason="langfuse keys set but the observability extra is not installed")
        return None
    return CallbackHandler()


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
