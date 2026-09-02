from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class FactorLabel(StrEnum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNCERTAIN = "UNCERTAIN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceItem(BaseModel):
    """One stored row a factor rests on, carried through verbatim so the
    consultant can check the claim against NetSuite themselves. data-rules.md:
    every ranked factor must be traceable to stored evidence — a bare record
    ID is not traceability."""

    source_id: str
    record_type: str | None = None
    field_name: str
    old_value: str | None = None
    new_value: str | None = None
    actor: str | None = None
    context: str | None = None
    occurred_at: datetime | None = None


class Factor(BaseModel):
    label: FactorLabel
    rank: int
    summary: str
    supporting_source_ids: list[str]
    #: The rows behind this factor. Empty only for factors that predate the
    #: field, never as a way of hiding thin evidence.
    evidence: list[EvidenceItem] = []


class Gap(BaseModel):
    description: str
    reason: str


class DiagnosisResult(BaseModel):
    target_source_id: str
    factors: list[Factor]
    gaps: list[Gap]
