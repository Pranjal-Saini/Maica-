from dataclasses import dataclass
from datetime import datetime

from maica.reasoning.patterns import (
    ACTOR_SYSTEM,
    ACTOR_UNATTRIBUTED,
    ACTOR_USER,
    CHANGE_FIRST_SET,
    CHANGE_MODIFIED,
    SORT_SMALLEST,
    build_field_groups,
    build_pattern_index,
    classify_actor,
    classify_change,
    value_facets,
)


@dataclass(frozen=True)
class _Row:
    field_name: str
    change_kind: str = CHANGE_MODIFIED
    actor_class: str = ACTOR_USER
    context: str | None = "UI"
    record_count: int = 1
    change_count: int = 1
    actors: tuple[str, ...] = ("jsmith",)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    day_count: int = 0


@dataclass(frozen=True)
class _Total:
    field_name: str
    record_count: int
    change_count: int = 1


@dataclass(frozen=True)
class _Facet:
    field_name: str
    distinct_values: int
    largest_value_count: int


def test_actor_classes_match_the_three_the_sql_produces() -> None:
    # aggregates._actor_class_case emits exactly these strings. If the two ever
    # disagree the drill-down silently returns nothing for a whole class.
    assert classify_actor("System") == ACTOR_SYSTEM
    assert classify_actor("  system  ") == ACTOR_SYSTEM
    assert classify_actor("jsmith") == ACTOR_USER
    assert classify_actor(None) == ACTOR_UNATTRIBUTED
    assert classify_actor("   ") == ACTOR_UNATTRIBUTED


def test_populating_an_empty_field_is_not_a_modification() -> None:
    assert classify_change("4000") == CHANGE_MODIFIED
    assert classify_change("") == CHANGE_FIRST_SET
    assert classify_change(None) == CHANGE_FIRST_SET


def test_groups_are_ordered_by_record_count_not_by_name() -> None:
    groups = build_field_groups(
        [_Total("Memo", 5), _Total("Account", 90)],
        [_Row("Memo", record_count=5), _Row("Account", record_count=90)],
    )

    assert [group.field_name for group in groups] == ["Account", "Memo"]


def test_the_consultant_can_invert_the_order_to_reach_outliers() -> None:
    # The largest group is the account's routine. Nothing scores the small
    # ones as more interesting — but one click has to reach them.
    groups = build_field_groups(
        [_Total("Memo", 5), _Total("Account", 90)],
        [_Row("Memo", record_count=5), _Row("Account", record_count=90)],
        sort=SORT_SMALLEST,
    )

    assert [group.field_name for group in groups] == ["Memo", "Account"]


def test_patterns_beyond_the_cap_are_declared_not_dropped() -> None:
    rows = [
        _Row("Account", context=f"CTX{i}", record_count=100 - i, actors=(f"user{i}",))
        for i in range(20)
    ]

    group = build_field_groups([_Total("Account", 100)], rows, max_patterns_per_field=12)[0]

    assert len(group.patterns) == 12
    assert group.hidden_pattern_count == 8
    assert "8 further patterns" in (group.hidden_reason or "")


def test_a_fully_shown_field_declares_nothing() -> None:
    group = build_field_groups([_Total("Account", 10)], [_Row("Account", record_count=10)])[0]

    assert group.hidden_pattern_count == 0
    assert group.hidden_reason is None


def test_a_system_pattern_is_described_as_automation_not_as_a_person() -> None:
    group = build_field_groups(
        [_Total("Account", 5)],
        [_Row("Account", actor_class=ACTOR_SYSTEM, context="SCHEDULED", actors=("System",))],
    )[0]
    pattern = group.patterns[0]

    assert pattern.is_automation
    assert "not a specific person" in pattern.describe()
    assert "SCHEDULED" in pattern.describe()


def test_a_missing_actor_says_so_rather_than_guessing() -> None:
    group = build_field_groups(
        [_Total("Account", 5)], [_Row("Account", actor_class=ACTOR_UNATTRIBUTED, actors=())]
    )[0]

    assert "did not record" in group.patterns[0].describe()


def test_a_pattern_never_claims_it_caused_anything() -> None:
    # Same restraint the factors carry: a count is not a finding.
    rows = [
        _Row("Account", actor_class=ACTOR_SYSTEM, context="SCHEDULED", actors=("System",)),
        _Row("Memo", change_kind=CHANGE_FIRST_SET, context=None, actors=()),
    ]
    index = build_pattern_index(
        [_Total("Account", 5), _Total("Memo", 3)],
        rows,
        total_records=8,
        records_with_change_evidence=8,
    )

    prose = " ".join(
        [pattern.describe() for group in index.groups for pattern in group.patterns]
        + [gap.description + gap.reason for gap in index.gaps]
        + [index.coverage.summary, index.coverage.counting_note]
    ).lower()

    for word in ("caused", "because", "due to", "responsible", "triggered", "explains why"):
        assert word not in prose


def test_a_missing_context_travels_as_a_flag_not_a_magic_string() -> None:
    # A context genuinely named "None" would otherwise be indistinguishable
    # from one that was never recorded.
    with_context = _Row("Account", context="UI")
    without = _Row("Account", context=None)

    a = build_field_groups([_Total("Account", 2)], [with_context])[0].patterns[0]
    b = build_field_groups([_Total("Account", 2)], [without])[0].patterns[0]

    assert a.query_params()["context"] == "UI"
    assert "context" not in b.query_params()
    assert b.query_params()["context_missing"] == "1"


def test_changes_landing_on_one_day_are_reported_as_such() -> None:
    when = datetime(2026, 7, 12, 9, 15)
    group = build_field_groups(
        [_Total("Account", 400)],
        [_Row("Account", record_count=400, first_seen=when, last_seen=when, day_count=1)],
    )[0]

    assert "all on 12 Jul 2026" in group.patterns[0].timing


def test_a_part_snapshot_analysis_says_how_much_it_covers() -> None:
    # Otherwise the groups read as covering the whole account.
    index = build_pattern_index(
        [_Total("Account", 120)],
        [_Row("Account", record_count=120)],
        total_records=5000,
        records_with_change_evidence=120,
    )

    assert index.coverage.is_partial
    assert any("120 of 5,000 records have change evidence" in g.description for g in index.gaps)


def test_a_snapshot_only_analysis_explains_why_there_are_no_patterns() -> None:
    index = build_pattern_index([], [], total_records=4951, records_with_change_evidence=0)

    assert index.groups == []
    assert any("No change patterns" in gap.description for gap in index.gaps)
    assert any("System Notes" in gap.reason for gap in index.gaps)


def test_full_coverage_raises_no_gap() -> None:
    index = build_pattern_index(
        [_Total("Account", 8)],
        [_Row("Account", record_count=8)],
        total_records=8,
        records_with_change_evidence=8,
    )

    assert not index.coverage.is_partial
    assert index.gaps == []


def test_an_empty_analysis_does_not_raise() -> None:
    index = build_pattern_index([], [], total_records=0, records_with_change_evidence=0)

    assert index.groups == []
    assert index.gaps == []


def test_value_facets_skip_near_unique_and_structural_columns() -> None:
    # Measured on the test account: Amount is near-unique per record and
    # divides nothing; Currency sits on a third of the ledger and divides
    # nothing either. Account and Memo are the usable ones.
    facets = value_facets(
        [
            _Facet("Amount", distinct_values=4848, largest_value_count=2),
            _Facet("Account", distinct_values=12, largest_value_count=436),
            _Facet("Memo", distinct_values=8, largest_value_count=644),
            _Facet("Currency", distinct_values=3, largest_value_count=1698),
        ],
        total_records=4951,
    )

    assert [facet.field_name for facet in facets] == ["Account", "Memo"]


def test_value_facets_on_an_empty_analysis_are_empty() -> None:
    assert value_facets([_Facet("Account", 12, 5)], total_records=0) == []
