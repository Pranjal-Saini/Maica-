from dataclasses import dataclass

from maica.reasoning.findings import (
    MIN_AFFECTED_FOR_CONFIDENCE,
    Separation,
    investigate,
)


@dataclass(frozen=True)
class _Row:
    field_name: str
    actor_class: str = "System"
    context: str | None = "SCHEDULED"
    in_affected: int = 0
    in_rest: int = 0


def test_a_key_on_every_affected_record_and_no_other_ranks_first() -> None:
    """The sharpest statement the evidence can make, and the one a consultant
    is looking for: this is what the broken ones have and the rest do not."""
    rows = [
        _Row("Amount", actor_class="user", context="UI", in_affected=30, in_rest=600),
        _Row("Account", in_affected=47, in_rest=0),
    ]

    result = investigate(rows, affected_total=47, rest_total=1200)

    assert result.findings[0].field_name == "Account"
    assert result.findings[0].separation is Separation.ONLY_IN_AFFECTED


def test_something_the_affected_records_skipped_is_also_a_finding() -> None:
    # "None of them went through approval, and 92% of everything else did" is
    # as much an answer as a shared change. Dropping it would hide half the
    # picture.
    rows = [_Row("Approval", actor_class="user", context="WORKFLOW", in_affected=0, in_rest=1100)]

    result = investigate(rows, affected_total=47, rest_total=1200)

    assert result.findings[0].separation is Separation.MISSING_FROM_AFFECTED


def test_a_key_equally_common_in_both_groups_is_not_ranked_at_all() -> None:
    rows = [
        _Row("Status", actor_class="user", context="UI", in_affected=24, in_rest=600),
        _Row("Account", in_affected=47, in_rest=0),
    ]

    result = investigate(rows, affected_total=47, rest_total=1200)

    assert [f.field_name for f in result.findings] == ["Account"]


def test_a_tiny_affected_cohort_is_labelled_not_ranked_confidently() -> None:
    # Two records agreeing on something is not evidence, however perfectly it
    # separates them.
    rows = [_Row("Account", in_affected=2, in_rest=0)]

    result = investigate(rows, affected_total=2, rest_total=1200)

    assert result.findings[0].separation is Separation.TOO_FEW
    assert not result.is_conclusive_enough
    assert "too few" in result.caveat.lower()
    assert "coincidence" in result.caveat


def test_a_cohort_at_the_threshold_is_judged_normally() -> None:
    rows = [_Row("Account", in_affected=MIN_AFFECTED_FOR_CONFIDENCE, in_rest=0)]

    result = investigate(rows, affected_total=MIN_AFFECTED_FOR_CONFIDENCE, rest_total=1200)

    assert result.findings[0].separation is Separation.ONLY_IN_AFFECTED
    assert result.is_conclusive_enough


def test_nothing_matching_the_description_says_so() -> None:
    result = investigate([], affected_total=0, rest_total=1200)

    assert "No records matched" in result.headline


def test_everything_matching_the_description_says_so() -> None:
    # There is no comparison to make when the cohort is the whole account.
    result = investigate([], affected_total=1200, rest_total=0)

    assert "nothing to compare them against" in result.headline


def test_no_separating_signal_is_reported_as_a_real_answer() -> None:
    rows = [_Row("Status", actor_class="user", context="UI", in_affected=24, in_rest=600)]

    result = investigate(rows, affected_total=47, rest_total=1200)

    assert result.findings == ()
    assert "Nothing in this evidence separates" in result.headline


def test_findings_beyond_the_cap_are_declared() -> None:
    rows = [_Row(f"Field{i}", context=f"CTX{i}", in_affected=47 - i, in_rest=0) for i in range(15)]

    result = investigate(rows, affected_total=47, rest_total=1200, max_findings=10)

    assert len(result.findings) == 10
    assert result.hidden_finding_count == 5


def test_counts_are_always_shown_so_the_reader_can_disagree() -> None:
    rows = [_Row("Account", in_affected=47, in_rest=3)]

    finding = investigate(rows, affected_total=47, rest_total=1200).findings[0]

    assert "47 of 47 affected records" in finding.counts()
    assert "3 of 1,200 others" in finding.counts()


def test_a_finding_never_claims_it_caused_the_problem() -> None:
    # Separation is not causation, and this vocabulary is deliberately distinct
    # from the CONFIRMED/LIKELY labels, which mean something else entirely.
    rows = [
        _Row("Account", in_affected=47, in_rest=0),
        _Row("Approval", actor_class="user", context="WORKFLOW", in_affected=0, in_rest=1100),
    ]
    result = investigate(rows, affected_total=47, rest_total=1200)

    prose = " ".join(
        [f.describe() + f.counts() + f.meaning for f in result.findings]
        + [result.headline, result.caveat]
    ).lower()

    for word in ("caused", "because", "due to", "responsible", "root cause", "proves"):
        assert word not in prose
    assert "not proof of a cause" in result.caveat
