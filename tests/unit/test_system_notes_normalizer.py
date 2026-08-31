from pathlib import Path
from uuid import uuid4

from maica.evidence.models import RawEvidence
from maica.evidence.normalizer import SystemNotesNormalizer, get_normalizer
from maica.ingest.system_notes import SystemNotesCsvSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _raw_evidence_from_fixture(name: str) -> RawEvidence:
    ingest_result = SystemNotesCsvSource().ingest((FIXTURES / name).read_bytes())
    return RawEvidence(
        id=uuid4(),
        tenant_id=uuid4(),
        analysis_id=uuid4(),
        source_type=ingest_result.request.source_type,
        request_made=ingest_result.request.request_detail,
        payload={"rows": ingest_result.rows},
        understood_summary={},
        unavailable_reason=ingest_result.unavailable_reason,
    )


def test_get_normalizer_returns_system_notes_normalizer_for_known_source_type() -> None:
    assert isinstance(get_normalizer("upload:system_notes_csv"), SystemNotesNormalizer)


def test_normalize_maps_one_row_to_one_draft_without_exploding() -> None:
    raw_evidence = _raw_evidence_from_fixture("system_notes_clean.csv")

    drafts, result = SystemNotesNormalizer().normalize(raw_evidence)

    assert result.rows_normalized == 3
    assert result.records_created == 3
    amount_draft = next(d for d in drafts if d.field_name == "Amount")
    assert amount_draft.source_id == "1001"
    assert amount_draft.old_value == "1500.00"
    assert amount_draft.new_value == "1800.00"
    assert amount_draft.actor == "jsmith"
    assert amount_draft.context == "UIF"


def test_normalize_reports_unparseable_occurred_at_as_a_note() -> None:
    raw_evidence = _raw_evidence_from_fixture("system_notes_messy.csv")

    drafts, result = SystemNotesNormalizer().normalize(raw_evidence)

    memo_draft = next(d for d in drafts if d.field_name == "Memo")
    assert memo_draft.occurred_at is None
    assert any("unparseable" in note for note in result.notes)
