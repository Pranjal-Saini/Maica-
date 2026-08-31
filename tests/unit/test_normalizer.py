from pathlib import Path
from uuid import uuid4

from maica.evidence.models import RawEvidence
from maica.evidence.normalizer import SavedSearchCsvNormalizer, get_normalizer
from maica.ingest.csv_saved_search import CsvSavedSearchSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _raw_evidence_from_fixture(name: str) -> RawEvidence:
    ingest_result = CsvSavedSearchSource().ingest((FIXTURES / name).read_bytes())
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


def test_get_normalizer_returns_saved_search_normalizer_for_known_source_type() -> None:
    assert isinstance(get_normalizer("upload:saved_search_csv"), SavedSearchCsvNormalizer)


def test_get_normalizer_returns_none_for_unknown_source_type() -> None:
    assert get_normalizer("something:unrecognized") is None


def test_normalize_explodes_each_row_into_one_draft_per_data_field() -> None:
    raw_evidence = _raw_evidence_from_fixture("saved_search_clean.csv")

    drafts, result = SavedSearchCsvNormalizer().normalize(raw_evidence)

    assert result.rows_normalized == 3
    assert result.rows_skipped == 0
    # clean fixture recognizes: entity, amount, account, memo (4 data fields per row)
    assert result.records_created == 12
    assert len(drafts) == 12

    first_row_drafts = [d for d in drafts if d.source_id == "1001"]
    assert {d.field_name for d in first_row_drafts} == {"entity", "amount", "account", "memo"}
    assert all(d.old_value is None for d in first_row_drafts)
    assert all(d.record_type == "Journal Entry" for d in first_row_drafts)
    assert all(d.occurred_at is not None for d in first_row_drafts)


def test_normalize_reports_unparseable_occurred_at_as_a_note() -> None:
    raw_evidence = _raw_evidence_from_fixture("saved_search_messy.csv")

    drafts, result = SavedSearchCsvNormalizer().normalize(raw_evidence)

    assert result.rows_normalized == 3
    unparsed_source = [d for d in drafts if d.source_id == "1002"]
    assert all(d.occurred_at is None for d in unparsed_source)
    assert any("occurred_at" in note and "unparseable" in note for note in result.notes)
