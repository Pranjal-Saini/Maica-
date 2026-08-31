import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from maica.evidence.db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="OPEN")
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RawEvidence(Base):
    """Insert-only. No update path is defined anywhere in the repository layer."""

    __tablename__ = "raw_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_or_uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    request_made: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    understood_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


Index(
    "ix_raw_evidence_tenant_analysis",
    RawEvidence.tenant_id,
    RawEvidence.analysis_id,
)


class Record(Base):
    """One field's value on one NetSuite record, normalized out of raw evidence.

    old_value and context are populated only by sources that carry change
    history (e.g. a System Notes export); a snapshot source like a saved
    search always leaves them null. Insert-only, same as RawEvidence — no
    update path exists."""

    __tablename__ = "records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id"), nullable=False, index=True
    )
    raw_evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("raw_evidence.id"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    record_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


Index(
    "ix_records_tenant_analysis_source",
    Record.tenant_id,
    Record.analysis_id,
    Record.source_id,
)
