import uuid

from anthropic import AsyncAnthropic
from fastapi import Header

from maica.config.settings import get_settings
from maica.evidence.db import get_db_session  # re-exported for route imports

__all__ = ["get_db_session", "get_current_tenant_id", "get_llm_client"]


async def get_current_tenant_id(
    x_tenant_id: str | None = Header(default=None),
) -> uuid.UUID:
    """The single seam where tenant identity enters a request. Dev-only header
    for now; real auth (session cookies + argon2) replaces this function's body
    later without touching any caller."""
    if x_tenant_id:
        return uuid.UUID(x_tenant_id)
    return get_settings().dev_tenant_id


async def get_llm_client() -> AsyncAnthropic | None:
    """None when no API key is configured — callers must degrade gracefully,
    not treat a missing key as an error."""
    api_key = get_settings().anthropic_api_key
    if not api_key:
        return None
    return AsyncAnthropic(api_key=api_key)
