import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from maica.evidence.db import Base


class User(Base):
    """A consultant's login. One User can access multiple client accounts
    (Tenants) via UserTenantAccess — a consulting firm works across clients,
    not one login per client."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class UserTenantAccess(Base):
    """Grants one User visibility into one Tenant (client account). Created
    automatically for whichever User creates a Tenant; extending access to
    other Users on the same team is not built yet."""

    __tablename__ = "user_tenant_access"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant_access"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
