"""The measure behind the shortlist.

    weight(key) = -ln(n / N) * ln(1 + n)

Tested in Python so the shape of the curve is pinned without a database. The
same expression is built in SQL in evidence/shortlist.py; these tests are what
that SQL is answerable to.
"""

from dataclasses import dataclass

from maica.evidence.shortlist import ShortlistReason, _weight
from maica.reasoning.phrasing import describe_reason


@dataclass(frozen=True)
class _Reason:
    field_name: str
    actor_class: str | None = None
    context: str | None = None
    value: str | None = None
    records_sharing: int = 1
    total_records: int = 100

    @property
    def share(self) -> float:
        return self.records_sharing / self.total_records


def test_a_key_on_every_record_is_free() -> None:
    # -ln(1) is 0, so the account's routine contributes nothing. Without this
    # the widest-reaching behaviour would dominate the ranking, which is the
    # opposite of useful.
    assert _weight(5000, 5000) == 0.0


def test_reach_damps_a_key_seen_exactly_once() -> None:
    """A key on one record alone is usually export noise. A key on fifteen is a
    real pattern that is still rare. The second factor is what separates them —
    without it the singleton would win every time, being the rarest thing."""
    lone = _weight(1, 5000)
    small_group = _weight(15, 5000)

    assert lone < small_group


def test_rarity_still_beats_ubiquity_at_equal_reach() -> None:
    rare_in_a_big_account = _weight(15, 5000)
    common_in_a_small_one = _weight(15, 20)

    assert rare_in_a_big_account > common_in_a_small_one


def test_the_curve_peaks_between_unique_and_universal() -> None:
    total = 5000
    weights = {n: _weight(n, total) for n in (1, 5, 25, 100, 1000, 4000, 5000)}
    peak = max(weights, key=lambda n: weights[n])

    assert 1 < peak < total
    assert weights[1] < weights[peak]
    assert weights[total] < weights[peak]


def test_several_rare_keys_outrank_one() -> None:
    one = _weight(12, 5000)
    three = sum(_weight(n, 5000) for n in (12, 18, 30))

    assert three > one


def test_degenerate_counts_do_not_raise() -> None:
    assert _weight(0, 100) == 0.0
    assert _weight(5, 0) == 0.0
    # A count above the total would make ln positive and flip the sign; clamped.
    assert _weight(200, 100) == 0.0


def test_a_reason_reports_its_own_share() -> None:
    reason = ShortlistReason(
        field_name="Account",
        actor_class="System",
        context="SCHEDULED",
        value=None,
        records_sharing=12,
        total_records=4996,
    )

    assert reason.share == 12 / 4996
    assert reason.weight == _weight(12, 4996)


def test_a_change_reason_names_who_and_where_with_counts() -> None:
    text = describe_reason(
        _Reason(
            field_name="Account",
            actor_class="System",
            context="SCHEDULED",
            records_sharing=12,
            total_records=4996,
        )
    )

    assert "Account changed" in text
    assert "not a specific person" in text
    assert "SCHEDULED" in text
    assert "12 of 4,996 records" in text


def test_a_value_reason_names_the_value() -> None:
    text = describe_reason(
        _Reason(field_name="Account", value="4010 - Service Revenue", records_sharing=3)
    )

    assert "4010 - Service Revenue" in text
    assert "3 of 100 records" in text


def test_a_tiny_share_is_not_rounded_away_to_zero_percent() -> None:
    text = describe_reason(_Reason(field_name="Account", records_sharing=1, total_records=5000))

    assert "under 0.1%" in text
    assert "0.0%" not in text


def test_a_reason_never_claims_the_record_is_wrong() -> None:
    # Being unlike the rest of an account is not evidence of being wrong. The
    # same deny-list the factor summaries answer to.
    prose = " ".join(
        describe_reason(reason)
        for reason in (
            _Reason("Account", actor_class="System", context="SCHEDULED", records_sharing=12),
            _Reason("Memo", actor_class="unattributed", records_sharing=4),
            _Reason("Amount", value="18400.00", records_sharing=2),
        )
    ).lower()

    for word in ("caused", "because", "due to", "responsible", "triggered", "wrong", "suspicious"):
        assert word not in prose


def test_actor_classes_match_the_three_the_sql_produces() -> None:
    # aggregates._actor_class_case emits exactly these strings. If the Python
    # and the SQL ever disagree, a whole class of records silently vanishes
    # from the comparison.
    from maica.reasoning.phrasing import (
        ACTOR_SYSTEM,
        ACTOR_UNATTRIBUTED,
        ACTOR_USER,
        classify_actor,
    )

    assert classify_actor("System") == ACTOR_SYSTEM
    assert classify_actor("  system  ") == ACTOR_SYSTEM
    assert classify_actor("jsmith") == ACTOR_USER
    assert classify_actor(None) == ACTOR_UNATTRIBUTED
    assert classify_actor("   ") == ACTOR_UNATTRIBUTED
