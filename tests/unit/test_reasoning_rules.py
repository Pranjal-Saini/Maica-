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
    fields_mentioned = {
        f.summary.split(" = ")[0].split("Correlation only: ")[1] for f in result.factors
    }
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
    drafts = [
        _change_draft(
            "1001", "Amount", "1500.00", "1800.00", "jsmith", "UIF", datetime(2026, 7, 12, 9, 14)
        )
    ]

    result = diagnose(drafts, "1001")

    assert len(result.factors) == 1
    # Fully documented: actor and timestamp both present, so the change itself
    # is proven — see test_change_label_tracks_how_documented_the_change_is.
    assert result.factors[0].label == FactorLabel.CONFIRMED
    assert "Amount went from '1500.00' to '1800.00'" in result.factors[0].summary
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

    assert "Amount went from" in result.factors[0].summary
    assert "Memo went from" in result.factors[1].summary


def test_diagnose_ranks_change_factors_before_shared_value_factors() -> None:
    drafts = [
        *_drafts_from_clean_fixture(),
        _change_draft("1001", "Amount", "1500.00", "1800.00", "jsmith"),
    ]

    result = diagnose(drafts, "1001")

    assert "Amount went from" in result.factors[0].summary


def test_change_label_tracks_how_documented_the_change_is() -> None:
    """The strong label is earned by the completeness of the audit entry, not
    by any judgement about cause. A row carrying old value, new value, actor
    and timestamp is something the consultant can open in NetSuite and see for
    themselves — that is what CONFIRMED claims, and all it claims."""
    documented = _change_draft(
        "1001", "Account", "4000", "4010", "System", "SCHEDULED", datetime(2026, 7, 12, 9, 15)
    )
    no_timestamp = _change_draft("1002", "Account", "4000", "4010", "System", "SCHEDULED")
    no_actor = _change_draft("1003", "Account", "4000", "4010", None, None, datetime(2026, 7, 12))

    assert diagnose([documented], "1001").factors[0].label == FactorLabel.CONFIRMED
    assert diagnose([no_timestamp], "1002").factors[0].label == FactorLabel.LIKELY
    assert diagnose([no_actor], "1003").factors[0].label == FactorLabel.LIKELY


def test_a_confirmed_change_never_claims_it_caused_the_outcome() -> None:
    # The whole basis for allowing CONFIRMED at all: the claim is scoped to the
    # change, so the summary must keep saying causation is not established.
    drafts = [
        _change_draft(
            "1001", "Account", "4000", "4010", "System", "SCHEDULED", datetime(2026, 7, 12, 9, 15)
        )
    ]

    summary = diagnose(drafts, "1001").factors[0].label, diagnose(drafts, "1001").factors[0].summary

    assert summary[0] == FactorLabel.CONFIRMED
    assert "NOT established" in summary[1]
    for causal_word in ("caused the outcome.", "led to", "resulted in", "because of"):
        assert causal_word not in summary[1]


def test_a_widely_shared_value_supports_no_conclusion() -> None:
    # A GL account on half the ledger is routine. Ranking it as a lead pads the
    # report with noise; INSUFFICIENT_EVIDENCE says so instead.
    target = _change_draft("1001", "Account", "x", "4010 - Service Revenue", "jsmith")
    others = [
        _change_draft(str(2000 + i), "Account", "x", "4010 - Service Revenue", "jsmith")
        for i in range(6)
    ]

    result = diagnose([target, *others], "1001")
    correlations = [f for f in result.factors if "Correlation only" in f.summary]

    assert correlations
    assert correlations[0].label == FactorLabel.INSUFFICIENT_EVIDENCE
    assert "no conclusion should be drawn" in correlations[0].summary


def test_a_narrowly_shared_value_stays_an_uncertain_lead() -> None:
    target = _change_draft("1001", "Account", "x", "4010 - Service Revenue", "jsmith")
    other = _change_draft("1002", "Account", "x", "4010 - Service Revenue", "jsmith")

    result = diagnose([target, other], "1001")
    correlations = [f for f in result.factors if "Correlation only" in f.summary]

    assert correlations[0].label == FactorLabel.UNCERTAIN
    assert "not a finding" in correlations[0].summary


def test_every_factor_carries_the_rows_it_rests_on() -> None:
    # data-rules.md: every ranked factor must be traceable to stored evidence.
    # A bare record ID is not traceability — the consultant needs the actual
    # field, values, actor, context and timestamp to check it in NetSuite.
    drafts = [
        _change_draft(
            "1001", "Account", "4000", "4010", "System", "SCHEDULED", datetime(2026, 7, 12, 9, 15)
        ),
        _change_draft(
            "1002", "Account", "3900", "4010", "mchen", "UI", datetime(2026, 7, 12, 9, 41)
        ),
    ]

    result = diagnose(drafts, "1001")

    assert all(f.evidence for f in result.factors)
    change = result.factors[0].evidence[0]
    assert change.source_id == "1001"
    assert change.field_name == "Account"
    assert change.old_value == "4000"
    assert change.new_value == "4010"
    assert change.actor == "System"
    assert change.context == "SCHEDULED"
    assert change.occurred_at == datetime(2026, 7, 12, 9, 15)


def test_correlation_evidence_includes_the_matching_row_on_the_other_record() -> None:
    target = _change_draft("1001", "Account", "4000", "4010", "System", "SCH")
    other = _change_draft("1002", "Account", "3900", "4010", "mchen", "UI")

    result = diagnose([target, other], "1001")
    correlation = next(f for f in result.factors if "Correlation only" in f.summary)

    assert {e.source_id for e in correlation.evidence} == {"1001", "1002"}


def test_altering_a_value_outranks_populating_an_empty_field() -> None:
    """A memo filled in for the first time used to rank above an account
    reclassification purely because it happened later, which sent "next thing
    worth looking at" to the least interesting event on the record."""
    memo_filled_in = _change_draft(
        "1001", "Memo", "", "Q3 retainer", "jsmith", "UI", datetime(2026, 7, 12, 11, 2)
    )
    account_changed = _change_draft(
        "1001", "Account", "4000", "4010", "System", "SCHEDULED", datetime(2026, 7, 12, 9, 15)
    )

    result = diagnose([memo_filled_in, account_changed], "1001")

    assert "Account went from" in result.factors[0].summary
    assert "Memo was first set to" in result.factors[1].summary
    assert "not an existing value being altered" in result.factors[1].summary


def test_recency_still_orders_changes_of_the_same_kind() -> None:
    older = _change_draft(
        "1001", "Status", "Pending", "Approved", "mchen", "UI", datetime(2026, 7, 12, 9, 10)
    )
    newer = _change_draft(
        "1001", "Account", "4000", "4010", "System", "SCH", datetime(2026, 7, 12, 9, 15)
    )

    result = diagnose([older, newer], "1001")

    assert "Account went from" in result.factors[0].summary
    assert "Status went from" in result.factors[1].summary
