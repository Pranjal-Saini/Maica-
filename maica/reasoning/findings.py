"""Ranking what separates the affected records from the rest.

Given two cohorts the consultant defined — the records that went wrong, and
everything else — this ranks each change signature by how sharply it tells them
apart. A key on every affected record and no other is the strongest statement
the evidence can make; one equally common in both says nothing at all.

The strength words describe **separation**, not causation, and are deliberately
a different vocabulary from FactorLabel in models.py. CONFIRMED there means a
change is documented in the audit trail. Reusing it here would silently promote
"this separates the two groups" into "this is proven to be the fault", which is
a different and much larger claim.

Two things keep it honest. Every finding carries both raw counts, so the
consultant can judge the separation themselves. And a cohort too small to
distinguish signal from coincidence is labelled as such rather than ranked —
three affected records agreeing on something is not yet evidence.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from maica.reasoning.phrasing import actor_phrase, context_phrase

#: Below this, a perfect separation is as likely to be chance as substance.
MIN_AFFECTED_FOR_CONFIDENCE = 3

#: A key must lead by this much prevalence to be worth a consultant's attention.
MEANINGFUL_LEAD = 0.2

#: Findings shown before the remainder is declared.
MAX_FINDINGS = 10


class Separation(StrEnum):
    ONLY_IN_AFFECTED = "ONLY IN AFFECTED"
    MORE_IN_AFFECTED = "MORE COMMON IN AFFECTED"
    MISSING_FROM_AFFECTED = "ABSENT FROM AFFECTED"
    NO_SIGNAL = "NO CLEARER THAN CHANCE"
    TOO_FEW = "TOO FEW RECORDS TO TELL"


SEPARATION_MEANINGS = {
    Separation.ONLY_IN_AFFECTED: (
        "every affected record has this and no other record does — the sharpest "
        "separation the evidence can show"
    ),
    Separation.MORE_IN_AFFECTED: "more common among the affected records than outside them",
    Separation.MISSING_FROM_AFFECTED: (
        "common outside the affected records but absent from them — something they did not go "
        "through"
    ),
    Separation.NO_SIGNAL: "about as common in both groups, so it distinguishes nothing",
    Separation.TOO_FEW: (
        "too few affected records for a difference to mean anything yet — a handful agreeing "
        "is not evidence"
    ),
}


class ContrastRowLike(Protocol):
    @property
    def field_name(self) -> str: ...
    @property
    def actor_class(self) -> str: ...
    @property
    def context(self) -> str | None: ...
    @property
    def in_affected(self) -> int: ...
    @property
    def in_rest(self) -> int: ...


@dataclass(frozen=True)
class Finding:
    field_name: str
    actor_class: str
    context: str | None
    in_affected: int
    affected_total: int
    in_rest: int
    rest_total: int
    separation: Separation

    @property
    def affected_share(self) -> float:
        return self.in_affected / self.affected_total if self.affected_total else 0.0

    @property
    def rest_share(self) -> float:
        return self.in_rest / self.rest_total if self.rest_total else 0.0

    @property
    def lead(self) -> float:
        return self.affected_share - self.rest_share

    @property
    def meaning(self) -> str:
        return SEPARATION_MEANINGS[self.separation]

    def describe(self) -> str:
        return (
            f"{self.field_name} changed {actor_phrase(self.actor_class)} "
            f"{context_phrase(self.context)}"
        )

    def counts(self) -> str:
        return (
            f"on {self.in_affected:,} of {self.affected_total:,} affected records "
            f"({self.affected_share:.0%}), and {self.in_rest:,} of {self.rest_total:,} "
            f"others ({self.rest_share:.0%})"
        )


@dataclass(frozen=True)
class Investigation:
    findings: tuple[Finding, ...]
    affected_total: int
    rest_total: int
    hidden_finding_count: int = 0

    @property
    def is_conclusive_enough(self) -> bool:
        return self.affected_total >= MIN_AFFECTED_FOR_CONFIDENCE

    @property
    def headline(self) -> str:
        """What the comparison actually established, in one line."""
        if not self.affected_total:
            return "No records matched that description, so there is nothing to compare."
        if not self.rest_total:
            return (
                f"All {self.affected_total:,} records in this analysis match that description, "
                "so there is nothing to compare them against."
            )
        top = self.findings[0] if self.findings else None
        if top is None or top.separation in (Separation.NO_SIGNAL, Separation.TOO_FEW):
            return (
                f"Nothing in this evidence separates the {self.affected_total:,} affected "
                f"records from the other {self.rest_total:,}."
            )
        return (
            f"Comparing {self.affected_total:,} affected records against "
            f"{self.rest_total:,} others."
        )

    @property
    def caveat(self) -> str:
        base = (
            "A difference between the two groups is not proof of a cause. It is what the "
            "evidence separates on; the conclusion is yours."
        )
        if not self.is_conclusive_enough:
            return (
                f"Only {self.affected_total} affected record"
                f"{'s' if self.affected_total != 1 else ''} were given, which is too few for a "
                "difference to mean much — anything shown here could as easily be coincidence. "
                + base
            )
        return base


def _classify(in_affected: int, affected_total: int, in_rest: int, rest_total: int) -> Separation:
    if affected_total < MIN_AFFECTED_FOR_CONFIDENCE:
        return Separation.TOO_FEW

    affected_share = in_affected / affected_total if affected_total else 0.0
    rest_share = in_rest / rest_total if rest_total else 0.0

    if in_affected == affected_total and in_rest == 0:
        return Separation.ONLY_IN_AFFECTED
    if in_affected == 0 and rest_share >= MEANINGFUL_LEAD:
        return Separation.MISSING_FROM_AFFECTED
    if affected_share - rest_share >= MEANINGFUL_LEAD:
        return Separation.MORE_IN_AFFECTED
    return Separation.NO_SIGNAL


def investigate(
    rows: Sequence[ContrastRowLike],
    *,
    affected_total: int,
    rest_total: int,
    max_findings: int = MAX_FINDINGS,
) -> Investigation:
    """Ranks the signatures by how sharply they separate the two cohorts.

    Ordering is by the size of the gap in prevalence, which is a measurement
    rather than a judgement. Signatures that separate nothing are dropped from
    the ranking and counted, so the page never pads itself with noise.
    """
    findings = [
        Finding(
            field_name=row.field_name,
            actor_class=row.actor_class,
            context=row.context,
            in_affected=row.in_affected,
            affected_total=affected_total,
            in_rest=row.in_rest,
            rest_total=rest_total,
            separation=_classify(row.in_affected, affected_total, row.in_rest, rest_total),
        )
        for row in rows
    ]

    ranked = [f for f in findings if f.separation is not Separation.NO_SIGNAL]
    ranked.sort(
        key=lambda f: (
            f.separation is not Separation.ONLY_IN_AFFECTED,
            -abs(f.lead),
            f.field_name,
            f.actor_class,
            f.context or "",
        )
    )
    kept = tuple(ranked[:max_findings])
    return Investigation(
        findings=kept,
        affected_total=affected_total,
        rest_total=rest_total,
        hidden_finding_count=max(0, len(ranked) - len(kept)),
    )
