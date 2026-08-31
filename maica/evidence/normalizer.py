from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel

from maica.evidence.models import RawEvidence

# Fields that describe the record itself rather than a data value on it — these
# populate dedicated NormalizedRecordDraft columns instead of becoming their own
# field rows.
_META_FIELDS = {"internal_id", "document_number", "occurred_at", "record_type", "actor"}
_SOURCE_ID_FIELDS = ("internal_id", "document_number")


class NormalizedRecordDraft(BaseModel):
    """One field's value on one NetSuite record. old_value and context are
    populated only by sources that carry change history (e.g. System Notes);
    a snapshot export like a saved search always leaves them null."""

    source_id: str
    record_type: str | None
    field_name: str
    old_value: str | None
    new_value: str | None
    actor: str | None
    context: str | None = None
    occurred_at: datetime | None


class NormalizationResult(BaseModel):
    records_created: int
    rows_normalized: int
    rows_skipped: int
    notes: list[str]


class Normalizer(ABC):
    """One interface per source_type. Downstream graph/reasoning code only ever
    consumes NormalizedRecordDraft/NormalizationResult, never a concrete
    subclass — mirrors the IngestSource seam in maica/ingest/interface.py."""

    @abstractmethod
    def normalize(
        self, raw_evidence: RawEvidence
    ) -> tuple[list[NormalizedRecordDraft], NormalizationResult]:
        raise NotImplementedError


def _try_parse_occurred_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class SavedSearchCsvNormalizer(Normalizer):
    """Explodes one saved-search CSV row into one NormalizedRecordDraft per
    data field, per the records data model in docs/tech-stack.md."""

    def normalize(
        self, raw_evidence: RawEvidence
    ) -> tuple[list[NormalizedRecordDraft], NormalizationResult]:
        rows: list[dict] = raw_evidence.payload.get("rows", [])
        drafts: list[NormalizedRecordDraft] = []
        notes: list[str] = []
        rows_skipped = 0

        for row in rows:
            source_id = next((row[f] for f in _SOURCE_ID_FIELDS if row.get(f)), None)
            if not source_id:
                rows_skipped += 1
                notes.append("row with no source_id survived ingest — skipped during normalization")
                continue

            record_type = row.get("record_type")
            actor = row.get("actor")
            occurred_at_raw = row.get("occurred_at")
            occurred_at = _try_parse_occurred_at(occurred_at_raw)
            if occurred_at_raw and occurred_at is None:
                notes.append(
                    f"source_id {source_id}: occurred_at '{occurred_at_raw}' unparseable, "
                    "stored as null"
                )

            for field_name, value in row.items():
                if field_name in _META_FIELDS:
                    continue
                drafts.append(
                    NormalizedRecordDraft(
                        source_id=source_id,
                        record_type=record_type,
                        field_name=field_name,
                        old_value=None,
                        new_value=value,
                        actor=actor,
                        occurred_at=occurred_at,
                    )
                )

        return drafts, NormalizationResult(
            records_created=len(drafts),
            rows_normalized=len(rows) - rows_skipped,
            rows_skipped=rows_skipped,
            notes=notes,
        )


class SystemNotesNormalizer(Normalizer):
    """Each System Notes row already represents exactly one field-level
    change, so no explosion is needed — one row becomes one
    NormalizedRecordDraft directly, unlike the saved-search CSV normalizer."""

    def normalize(
        self, raw_evidence: RawEvidence
    ) -> tuple[list[NormalizedRecordDraft], NormalizationResult]:
        rows: list[dict] = raw_evidence.payload.get("rows", [])
        drafts: list[NormalizedRecordDraft] = []
        notes: list[str] = []
        rows_skipped = 0

        for row in rows:
            source_id = next((row[f] for f in _SOURCE_ID_FIELDS if row.get(f)), None)
            field_name = row.get("field_name")
            if not source_id or not field_name:
                rows_skipped += 1
                notes.append(
                    "row missing source_id or field name survived ingest — "
                    "skipped during normalization"
                )
                continue

            occurred_at_raw = row.get("occurred_at")
            occurred_at = _try_parse_occurred_at(occurred_at_raw)
            if occurred_at_raw and occurred_at is None:
                notes.append(
                    f"source_id {source_id}: occurred_at '{occurred_at_raw}' unparseable, "
                    "stored as null"
                )

            drafts.append(
                NormalizedRecordDraft(
                    source_id=source_id,
                    record_type=row.get("record_type"),
                    field_name=field_name,
                    old_value=row.get("old_value"),
                    new_value=row.get("new_value"),
                    actor=row.get("actor"),
                    context=row.get("context"),
                    occurred_at=occurred_at,
                )
            )

        return drafts, NormalizationResult(
            records_created=len(drafts),
            rows_normalized=len(rows) - rows_skipped,
            rows_skipped=rows_skipped,
            notes=notes,
        )


NORMALIZERS: dict[str, Normalizer] = {
    "upload:saved_search_csv": SavedSearchCsvNormalizer(),
    "upload:system_notes_csv": SystemNotesNormalizer(),
}


def get_normalizer(source_type: str) -> Normalizer | None:
    return NORMALIZERS.get(source_type)
