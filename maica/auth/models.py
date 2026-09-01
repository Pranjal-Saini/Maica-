import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from maica.evidence.db import Base


class User(Base):
    """A consultant's login, authenticated via Google Sign-In only — there is
    no password. One User can access multiple client accounts (Tenants) via
    UserTenantAccess — a consulting firm works across clients, not one login
    per client.

    google_sub (Google's stable, unique subject identifier) is the true
    identity, not email — Google's own guidance is that email can change
    while sub does not."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_sub: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
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
