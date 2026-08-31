from datetime import datetime
from pathlib import Path
from uuid import uuid4

from maica.evidence.models import RawEvidence
from maica.evidence.normalizer import NormalizedRecordDraft, SavedSearchCsvNormalizer
from maica.ingest.csv_saved_search import CsvSavedSearchSource
from maica.reasoning.models import FactorLabel
from maica.reasoning.rules import diagnose

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _drafts_from_clean_fixture() -> list[NormalizedRecordDraft]:
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    ingest_result = CsvSavedSearchSource().ingest(csv_bytes)
    raw_evidence = RawEvidence(
        id=uuid4(),
        tenant_id=uuid4(),
        analysis_id=uuid4(),
        source_type=ingest_result.request.source_type,
        request_made=ingest_result.request.request_detail,
        payload={"rows": ingest_result.rows},
        understood_summary={},
        unavailable_reason=ingest_result.unavailable_reason,
    )
    drafts, _ = SavedSearchCsvNormalizer().normalize(raw_evidence)
    return drafts


def test_diagnose_ranks_shared_field_factors_by_specificity() -> None:
    # 1001 shares account (with 1003, 1 other) and entity (with 1002, 1 other) —
    # both ties at "1 other record", so both should appear as UNCERTAIN factors.
    drafts = _drafts_from_clean_fixture()

    result = diagnose(drafts, "1001")

    assert len(result.factors) == 2
    assert all(f.label == FactorLabel.UNCERTAIN for f in result.factors)
    fields_mentioned = {f.summary.split(" = ")[0].split("Shares ")[1] for f in result.factors}
    assert fields_mentioned == {"account", "entity"}
    assert [f.rank for f in result.factors] == [1, 2]


def test_diagnose_reports_no_shared_field_gap_when_isolated() -> None:
    drafts = _drafts_from_clean_fixture()

    # 1002's account (2100 - AP) and memo/amount are unique to it, but it
    # shares entity with 1001, so use a record with truly no overlaps instead:
    isolated = [d for d in drafts if d.source_id != "1001" and d.source_id != "1002"]
    result = diagnose(isolated, "1003")

    assert result.factors == []
    assert any("No shared-field relationships" in g.description for g in result.gaps)


def test_diagnose_reports_actor_gap_when_no_actor_present() -> None:
    drafts = _drafts_from_clean_fixture()

    result = diagnose(drafts, "1001")

    assert any("No actor/user information" in g.description for g in result.gaps)


def test_diagnose_always_reports_no_change_evidence_gap() -> None:
    drafts = _drafts_from_clean_fixture()

    result = diagnose(drafts, "1001")

    assert any(
        "No script, workflow, integration, or configuration-change evidence" in g.description
        for g in result.gaps
    )


def test_diagnose_of_unknown_source_id_reports_not_found_gap() -> None:
    drafts = _drafts_from_clean_fixture()

    result = diagnose(drafts, "9999")

    assert result.factors == []
    assert len(result.gaps) == 1
    assert "9999" in result.gaps[0].description


def _change_draft(
    source_id: str,
    field_name: str,
    old_value: str,
    new_value: str,
    actor: str | None,
    context: str | None = None,
    occurred_at: datetime | None = None,
) -> NormalizedRecordDraft:
    return NormalizedRecordDraft(
        source_id=source_id,
        record_type="Journal Entry",
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        actor=actor,
        context=context,
        occurred_at=occurred_at,
    )


def test_diagnose_surfaces_field_change_factor_from_change_evidence() -> None:
    drafts = [_change_draft("1001", "Amount", "1500.00", "1800.00", "jsmith", "UIF")]

    result = diagnose(drafts, "1001")

    assert len(result.factors) == 1
    assert result.factors[0].label == FactorLabel.UNCERTAIN
    assert "Amount changed from '1500.00' to '1800.00'" in result.factors[0].summary
    assert "jsmith" in result.factors[0].summary
    assert not any(
        "No script, workflow, integration, or configuration-change evidence" in g.description
        for g in result.gaps
    )


def test_diagnose_hedges_system_actor_as_not_necessarily_manual() -> None:
    drafts = [_change_draft("1001", "Status", "Pending", "Approved", "System", "SCH")]

    result = diagnose(drafts, "1001")

    summary = result.factors[0].summary
    assert "System" in summary
    assert "not a specific person" in summary


def test_diagnose_ranks_change_factors_most_recent_first() -> None:
    older = _change_draft("1001", "Memo", "a", "b", "jsmith", occurred_at=datetime(2026, 1, 1))
    newer = _change_draft("1001", "Amount", "1", "2", "jsmith", occurred_at=datetime(2026, 1, 20))
    drafts = [older, newer]

    result = diagnose(drafts, "1001")

    assert result.factors[0].summary.startswith("Amount")
    assert result.factors[1].summary.startswith("Memo")


def test_diagnose_ranks_change_factors_before_shared_value_factors() -> None:
    drafts = [
        *_drafts_from_clean_fixture(),
        _change_draft("1001", "Amount", "1500.00", "1800.00", "jsmith"),
    ]

    result = diagnose(drafts, "1001")

    assert result.factors[0].summary.startswith("Amount changed")
