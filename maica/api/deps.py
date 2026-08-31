import uuid

from anthropic import AsyncAnthropic
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from maica.auth import repository as auth_repository
from maica.auth.models import User
from maica.config.settings import get_settings
from maica.evidence.db import get_db_session  # re-exported for route imports

__all__ = ["get_db_session", "get_current_user", "get_authorized_tenant_id", "get_llm_client"]


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    user = await auth_repository.get_user_by_id(session, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return user


async def get_authorized_tenant_id(
    tenant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> uuid.UUID:
    """The single seam where tenant identity enters a request. Every
    tenant-scoped route takes tenant_id as a path parameter and depends on
    this — it 403s unless the logged-in user has been granted access to that
    tenant, replacing the old dev-only X-Tenant-Id header."""
    has_access = await auth_repository.user_has_tenant_access(session, user.id, tenant_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="no access to this tenant"
        )
    return tenant_id


async def get_llm_client() -> AsyncAnthropic | None:
    """None when no API key is configured — callers must degrade gracefully,
    not treat a missing key as an error."""
    api_key = get_settings().anthropic_api_key
    if not api_key:
        return None
    return AsyncAnthropic(api_key=api_key)
