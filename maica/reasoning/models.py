from enum import StrEnum

from pydantic import BaseModel


class FactorLabel(StrEnum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNCERTAIN = "UNCERTAIN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Factor(BaseModel):
    label: FactorLabel
    rank: int
    summary: str
    supporting_source_ids: list[str]


class Gap(BaseModel):
    description: str
    reason: str


class DiagnosisResult(BaseModel):
    target_source_id: str
    factors: list[Factor]
    gaps: list[Gap]
