import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.auth.google_oauth import GoogleUserInfo
from maica.auth.models import User, UserTenantAccess
from maica.evidence.models import Tenant


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_google_sub(session: AsyncSession, google_sub: str) -> User | None:
    stmt = select(User).where(User.google_sub == google_sub)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession, *, google_sub: str, email: str, name: str | None
) -> User:
    user = User(google_sub=google_sub, email=email, name=name)
    session.add(user)
    await session.flush()
    return user


async def get_or_create_user_from_google(
    session: AsyncSession, google_user: GoogleUserInfo
) -> User:
    """The find-or-create step for Google Sign-In: google_sub is the durable
    identity, so an existing user is matched on that, not on email."""
    existing = await get_user_by_google_sub(session, google_user.sub)
    if existing is not None:
        return existing
    return await create_user(
        session, google_sub=google_user.sub, email=google_user.email, name=google_user.name
    )


async def create_tenant_for_user(session: AsyncSession, user_id: uuid.UUID, name: str) -> Tenant:
    tenant = Tenant(name=name)
    session.add(tenant)
    await session.flush()
    session.add(UserTenantAccess(user_id=user_id, tenant_id=tenant.id))
    await session.flush()
    return tenant


async def user_has_tenant_access(
    session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> bool:
    stmt = select(UserTenantAccess).where(
        UserTenantAccess.user_id == user_id, UserTenantAccess.tenant_id == tenant_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def list_tenants_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[Tenant]:
    stmt = (
        select(Tenant)
        .join(UserTenantAccess, UserTenantAccess.tenant_id == Tenant.id)
        .where(UserTenantAccess.user_id == user_id)
        .order_by(Tenant.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Drops the client account itself and every grant into it. Call after the
    evidence repository has cleared the data that references this tenant."""
    await session.execute(
        sa_delete(UserTenantAccess).where(UserTenantAccess.tenant_id == tenant_id)
    )
    await session.execute(sa_delete(Tenant).where(Tenant.id == tenant_id))
