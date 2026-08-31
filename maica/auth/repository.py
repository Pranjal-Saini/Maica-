import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.auth.models import User, UserTenantAccess
from maica.evidence.models import Tenant


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def create_user(session: AsyncSession, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    await session.flush()
    return user


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
