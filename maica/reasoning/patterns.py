"""Grouping an analysis's changes into readable patterns.

`diagnose()` in rules.py ranks factors *within* one record. That is useless when
the consultant does not yet know which record to open: a real account has
thousands, and listing them all just moves the problem.

This module answers the other question — *what has been happening in this
account* — by collapsing every recorded change into a small set of patterns:
"Account modified by System via SCHEDULED, on 487 records". A consultant reads
a few dozen of those instead of scrolling ten thousand cards.

Patterns are counts, not conclusions. Nothing here scores a record, ranks one
group above another as more suspicious, or suggests a pattern caused anything —
the same restraint reasoning-rules.md imposes on factors. The default order is
by record count, which is a fact about the evidence rather than a judgement
about it, and the consultant can reverse it.

Nothing in this module calls diagnose(). The deep dive is a pure aggregate
page, which is what keeps it cheap no matter how large the account is.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from maica.reasoning.models import Gap
from maica.reasoning.rules import STRUCTURAL_SHARE_RATIO

#: An actor is either NetSuite's automated `System`, a named person, or absent.
#: rules.py already refuses to read `System` as proof of a manual action; the
#: same caution applies here — it names who the trail recorded, nothing more.
ACTOR_SYSTEM = "System"
ACTOR_USER = "user"
ACTOR_UNATTRIBUTED = "unattributed"

#: Altering an existing value and populating an empty one are different events,
#: and rules.py already separates them (see _is_modification there). Grouping
#: them together would label a field's first population as a change.
CHANGE_MODIFIED = "modified"
CHANGE_FIRST_SET = "first set"

#: Patterns shown per field before the rest are declared rather than rendered.
MAX_PATTERNS_PER_FIELD = 12

#: Records listed on one drill-down page.
RECORDS_PER_PAGE = 100

SORT_LARGEST = "largest"
SORT_SMALLEST = "smallest"
SORT_FIELD = "field"
SORTS = (SORT_LARGEST, SORT_SMALLEST, SORT_FIELD)


def classify_actor(actor: str | None) -> str:
    """Collapses a raw actor into one of three classes.

    The same rule is expressed in SQL by `aggregates._actor_class_case` so the
    grouping can be counted in the database. If one changes, change both —
    tests/unit/test_patterns.py asserts they agree.
    """
    cleaned = (actor or "").strip()
    if not cleaned:
        return ACTOR_UNATTRIBUTED
    if cleaned.lower() == "system":
        return ACTOR_SYSTEM
    return ACTOR_USER


def classify_change(old_value: str | None) -> str:
    """Mirrors aggregates._change_kind_case, and rules.py's _is_modification."""
    return CHANGE_MODIFIED if (old_value or "").strip() else CHANGE_FIRST_SET


@dataclass(frozen=True)
class ChangePattern:
    """One (field, change kind, actor class, context) group.

    `record_count` is distinct records, not change rows: a record edited six
    times counts once. It is counted in SQL rather than by summing per-actor
    groups, which would count a record twice when two different people touched
    the same field.
    """

    field_name: str
    change_kind: str
    actor_class: str
    context: str | None
    record_count: int
    change_count: int
    actors: tuple[str, ...]
    first_seen: datetime | None
    last_seen: datetime | None
    day_count: int = 0

    @property
    def is_automation(self) -> bool:
        """Whether the audit trail attributes this to NetSuite's automation.

        Deliberately keyed on the actor alone. Deciding which execution
        contexts count as "automated" would mean asserting a NetSuite taxonomy
        this codebase has not verified — the context is shown, not interpreted.
        """
        return self.actor_class == ACTOR_SYSTEM

    @property
    def actor_phrase(self) -> str:
        if self.actor_class == ACTOR_SYSTEM:
            return "by System (an automated process, not a specific person)"
        if self.actor_class == ACTOR_UNATTRIBUTED:
            return "by an actor this export did not record"
        if len(self.actors) == 1:
            return f"by {self.actors[0]}"
        return f"by {len(self.actors)} different people"

    @property
    def context_phrase(self) -> str:
        return f"via {self.context}" if self.context else "with no context recorded"

    def describe(self) -> str:
        return f"{self.field_name} {self.change_kind} {self.actor_phrase}, {self.context_phrase}"

    @property
    def timing(self) -> str:
        """A factual note, not a flag. Changes landing on a single day read as
        a batch; the consultant draws that conclusion, not this module."""
        if self.first_seen is None or self.last_seen is None:
            return "no usable timestamps"
        span = f"{self.first_seen.strftime('%d %b %Y')} – {self.last_seen.strftime('%d %b %Y')}"
        if self.day_count == 1:
            return f"all on {self.first_seen.strftime('%d %b %Y')}"
        return f"{span} ({self.day_count} days)" if self.day_count else span

    def query_params(self) -> dict[str, str]:
        """The drill-down link. `context` is nullable, so absence travels as an
        explicit flag — a magic string would collide with a real context that
        happened to be named the same."""
        params = {
            "field": self.field_name,
            "change_kind": self.change_kind,
            "actor_class": self.actor_class,
        }
        if self.context is None:
            params["context_missing"] = "1"
        else:
            params["context"] = self.context
        return params


@dataclass(frozen=True)
class FieldGroup:
    """Every pattern touching one field, plus the field's own totals."""

    field_name: str
    record_count: int
    change_count: int
    patterns: tuple[ChangePattern, ...]
    hidden_pattern_count: int = 0

    @property
    def hidden_reason(self) -> str | None:
        """Stated, never silent — hard-rules.md forbids discarding evidence
        without saying so."""
        if not self.hidden_pattern_count:
            return None
        smallest = self.patterns[-1].record_count if self.patterns else 0
        plural = self.hidden_pattern_count != 1
        return (
            f"{self.hidden_pattern_count} further pattern{'s' if plural else ''} on this "
            f"field {'are' if plural else 'is'} not shown — each affects "
            f"{smallest} record{'s' if smallest != 1 else ''} or fewer."
        )


class PatternRowLike(Protocol):
    """One aggregate row as the database returns it, before grouping by field.

    A structural type, like graph.builder.RecordLike: it lets this module state
    what it needs without evidence/ having to import reasoning/ to satisfy it.
    Declared as properties so a frozen dataclass satisfies it — a plain
    annotation would demand a settable attribute.
    """

    @property
    def field_name(self) -> str: ...
    @property
    def change_kind(self) -> str: ...
    @property
    def actor_class(self) -> str: ...
    @property
    def context(self) -> str | None: ...
    @property
    def record_count(self) -> int: ...
    @property
    def change_count(self) -> int: ...
    @property
    def actors(self) -> tuple[str, ...]: ...
    @property
    def first_seen(self) -> datetime | None: ...
    @property
    def last_seen(self) -> datetime | None: ...
    @property
    def day_count(self) -> int: ...


class FieldTotalLike(Protocol):
    """Per-field distinct-record totals, counted in SQL for the same reason
    ChangePattern.record_count is: summing the patterns would count a record
    twice when its field was touched by more than one actor class."""

    @property
    def field_name(self) -> str: ...
    @property
    def record_count(self) -> int: ...
    @property
    def change_count(self) -> int: ...


@dataclass(frozen=True)
class Coverage:
    """What the patterns on this page actually account for.

    Without this the page misleads twice over: a consultant reading change
    patterns on a part-snapshot analysis assumes they cover the account, and
    one adding up the card counts gets a number far larger than the record
    total and concludes the tool is broken.
    """

    total_records: int
    records_with_change_evidence: int
    field_count: int
    pattern_count: int

    @property
    def is_partial(self) -> bool:
        return self.records_with_change_evidence < self.total_records

    @property
    def summary(self) -> str:
        plural = self.total_records != 1
        return (
            f"{self.total_records:,} record{'s' if plural else ''} · "
            f"{self.field_count} field{'s' if self.field_count != 1 else ''} changed · "
            f"{self.pattern_count} pattern{'s' if self.pattern_count != 1 else ''}"
        )


def coverage_gaps(coverage: Coverage) -> list[Gap]:
    """Named omissions, in the same shape the report page already renders."""
    gaps: list[Gap] = []
    if coverage.total_records and coverage.records_with_change_evidence == 0:
        gaps.append(
            Gap(
                description="No change patterns could be built for this analysis.",
                reason=(
                    "Only snapshot evidence (a saved-search CSV) was uploaded. A saved "
                    "search records what values are, not what changed, so there is no old "
                    "value, actor or context to group on. Upload a System Notes export to "
                    "group by who changed what, and in what context."
                ),
            )
        )
    elif coverage.is_partial:
        missing = coverage.total_records - coverage.records_with_change_evidence
        gaps.append(
            Gap(
                description=(
                    f"{coverage.records_with_change_evidence:,} of "
                    f"{coverage.total_records:,} records have change evidence."
                ),
                reason=(
                    f"The other {missing:,} appear only in snapshot evidence, so no change "
                    "pattern can include them. These groups describe part of the account, "
                    "not all of it."
                ),
            )
        )
    return gaps


@dataclass
class PatternIndex:
    """Everything the deep-dive page renders."""

    groups: list[FieldGroup] = field(default_factory=list)
    coverage: Coverage = field(default_factory=lambda: Coverage(0, 0, 0, 0))
    gaps: list[Gap] = field(default_factory=list)
    sort: str = SORT_LARGEST


def build_field_groups(
    field_totals: Sequence[FieldTotalLike],
    pattern_rows: Sequence[PatternRowLike],
    *,
    max_patterns_per_field: int = MAX_PATTERNS_PER_FIELD,
    sort: str = SORT_LARGEST,
) -> list[FieldGroup]:
    """Assembles the two aggregate queries into the page's structure.

    Default order is record count descending at both levels. That is a count,
    not a verdict: the largest group is the account's normal behaviour at least
    as often as it is the problem. `sort` lets the consultant invert it, which
    is how an outlier is reached without the tool ranking anything.
    """
    patterns_by_field: dict[str, list[ChangePattern]] = {}
    for row in pattern_rows:
        patterns_by_field.setdefault(row.field_name, []).append(
            ChangePattern(
                field_name=row.field_name,
                change_kind=row.change_kind,
                actor_class=row.actor_class,
                context=row.context,
                record_count=row.record_count,
                change_count=row.change_count,
                actors=tuple(row.actors),
                first_seen=row.first_seen,
                last_seen=row.last_seen,
                day_count=row.day_count,
            )
        )

    ascending = sort == SORT_SMALLEST
    groups: list[FieldGroup] = []
    for total in field_totals:
        found = sorted(
            patterns_by_field.get(total.field_name, []),
            # Ties broken on the key so paging and tests are deterministic.
            key=lambda pattern: (
                pattern.record_count if ascending else -pattern.record_count,
                pattern.change_kind,
                pattern.actor_class,
                pattern.context or "",
            ),
        )
        kept = tuple(found[:max_patterns_per_field])
        groups.append(
            FieldGroup(
                field_name=total.field_name,
                record_count=total.record_count,
                change_count=total.change_count,
                patterns=kept,
                hidden_pattern_count=max(0, len(found) - len(kept)),
            )
        )

    if sort == SORT_FIELD:
        groups.sort(key=lambda group: group.field_name)
    elif ascending:
        groups.sort(key=lambda group: (group.record_count, group.field_name))
    else:
        groups.sort(key=lambda group: (-group.record_count, group.field_name))
    return groups


def build_pattern_index(
    field_totals: Sequence[FieldTotalLike],
    pattern_rows: Sequence[PatternRowLike],
    *,
    total_records: int,
    records_with_change_evidence: int,
    sort: str = SORT_LARGEST,
) -> PatternIndex:
    sort = sort if sort in SORTS else SORT_LARGEST
    groups = build_field_groups(field_totals, pattern_rows, sort=sort)
    coverage = Coverage(
        total_records=total_records,
        records_with_change_evidence=records_with_change_evidence,
        field_count=len(groups),
        pattern_count=sum(len(g.patterns) + g.hidden_pattern_count for g in groups),
    )
    return PatternIndex(groups=groups, coverage=coverage, gaps=coverage_gaps(coverage), sort=sort)


@dataclass(frozen=True)
class ValueFacet:
    """A field whose values divide the account usefully.

    The fallback for an analysis with no change history at all: a saved-search
    export still says what values records hold, even though it cannot say what
    changed.
    """

    field_name: str
    distinct_values: int
    largest_share: float


class ValueFacetRowLike(Protocol):
    @property
    def field_name(self) -> str: ...
    @property
    def distinct_values(self) -> int: ...
    @property
    def largest_value_count(self) -> int: ...


#: A field with more distinct values than this is closer to an identifier than
#: a category — grouping on it returns one group per record.
MAX_FACET_VALUES = 50


def value_facets(
    rows: Sequence[ValueFacetRowLike],
    *,
    total_records: int,
    max_distinct: int = MAX_FACET_VALUES,
) -> list[ValueFacet]:
    """Picks the fields worth grouping on, from the account's own shape.

    Two ways a field is useless here, both read off the data rather than
    assumed from the field's name: an amount is near-unique per record and
    divides nothing, and a currency present on a third of the ledger is
    structural. The upper bound is STRUCTURAL_SHARE_RATIO, the same threshold
    rules.py uses to decide a shared value isolates nothing — one number, so
    the deep dive and the report page cannot disagree about the same field.
    """
    if not total_records:
        return []

    facets = []
    for row in rows:
        if not 2 <= row.distinct_values <= max_distinct:
            continue
        share = row.largest_value_count / total_records
        if share > STRUCTURAL_SHARE_RATIO:
            continue
        facets.append(
            ValueFacet(
                field_name=row.field_name,
                distinct_values=row.distinct_values,
                largest_share=share,
            )
        )
    facets.sort(key=lambda facet: (-facet.distinct_values, facet.field_name))
    return facets


class ShortlistReasonLike(Protocol):
    """One signature key behind a shortlisted record. Structural, so evidence/
    keeps not importing reasoning/."""

    @property
    def field_name(self) -> str: ...
    @property
    def actor_class(self) -> str | None: ...
    @property
    def context(self) -> str | None: ...
    @property
    def value(self) -> str | None: ...
    @property
    def records_sharing(self) -> int: ...
    @property
    def total_records(self) -> int: ...
    @property
    def share(self) -> float: ...


def describe_reason(reason: ShortlistReasonLike) -> str:
    """Why a record was shortlisted, in counts the consultant can check.

    States what is unusual about the record and how unusual, and stops there.
    Being unlike the rest of an account is not evidence of being wrong, so
    nothing here says caused, explains or responsible — the same restraint the
    factor summaries carry.
    """
    if reason.value is not None:
        what = f"{reason.field_name} = {reason.value!r}"
    else:
        who = {
            ACTOR_SYSTEM: "by System (an automated process, not a specific person)",
            ACTOR_UNATTRIBUTED: "by an actor this export did not record",
        }.get(reason.actor_class or "", "by a named user")
        where = f" via {reason.context}" if reason.context else " with no context recorded"
        what = f"{reason.field_name} changed {who}{where}"

    share = reason.share * 100
    shown = f"{share:.1f}%" if share >= 0.1 else "under 0.1%"
    plural = reason.records_sharing != 1
    return (
        f"{what} — on {reason.records_sharing:,} of {reason.total_records:,} "
        f"record{'s' if plural else ''} in this analysis ({shown})"
    )
