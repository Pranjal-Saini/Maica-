from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class AnalysisCreate(BaseModel):
    created_by: str


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: str
    created_by: str
    created_at: datetime


class UnderstoodSummary(BaseModel):
    rows_understood: int
    rows_skipped: int
    columns_recognized: list[str]
    columns_ignored: list[str]
    skip_reasons: list[str] = []


class RawEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    analysis_id: UUID
    source_type: str
    fetched_or_uploaded_at: datetime
    request_made: dict
    understood_summary: UnderstoodSummary
    unavailable_reason: str | None


class RecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: str
    record_type: str | None
    field_name: str
    old_value: str | None
    new_value: str | None
    actor: str | None
    occurred_at: datetime | None


class FileUploadResult(BaseModel):
    """One uploaded file's outcome. A file whose type could not be recognised
    reports that in `unrecognised_reason` and is skipped, rather than being
    guessed at and normalized into the wrong shape."""

    filename: str
    evidence_type: str | None
    unrecognised_reason: str | None = None
    raw_evidence: RawEvidenceRead | None = None
    records_created: int = 0
    normalization_notes: list[str] = []


class UploadResponse(BaseModel):
    analysis_id: UUID
    tenant_id: UUID
    files: list[FileUploadResult]
    records_created: int
