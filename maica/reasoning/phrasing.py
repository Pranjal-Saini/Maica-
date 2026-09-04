"""How the evidence is described to a consultant.

Small and shared on purpose: the record shortlist and the cohort comparison
both name the same things — a field, who changed it, in what context — and
they must say it the same way, or the two surfaces read as two tools.

The restraint here is the same one reasoning-rules.md puts on factors. These
functions describe what the audit trail recorded and how often; none of them
says anything caused anything.
"""

from typing import Protocol

#: An actor is either NetSuite's automated `System`, a named person, or absent.
#: rules.py already refuses to read `System` as proof of a manual action; the
#: same caution applies here — it names who the trail recorded, nothing more.
ACTOR_SYSTEM = "System"
ACTOR_USER = "user"
ACTOR_UNATTRIBUTED = "unattributed"


def classify_actor(actor: str | None) -> str:
    """Collapses a raw actor into one of three classes.

    The same rule is expressed in SQL by `aggregates._actor_class_case` so the
    grouping can be counted in the database. If one changes, change both —
    tests/unit/test_phrasing.py asserts they agree.
    """
    cleaned = (actor or "").strip()
    if not cleaned:
        return ACTOR_UNATTRIBUTED
    if cleaned.lower() == "system":
        return ACTOR_SYSTEM
    return ACTOR_USER


def actor_phrase(actor_class: str | None) -> str:
    if actor_class == ACTOR_SYSTEM:
        return "by System (an automated process, not a specific person)"
    if actor_class == ACTOR_UNATTRIBUTED:
        return "by an actor this export did not record"
    return "by a named user"


def context_phrase(context: str | None) -> str:
    return f"via {context}" if context else "with no context recorded"


class ShortlistReasonLike(Protocol):
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
    Being unlike the rest of an account is not evidence of being wrong.
    """
    if reason.value is not None:
        what = f"{reason.field_name} = {reason.value!r}"
    else:
        what = (
            f"{reason.field_name} changed {actor_phrase(reason.actor_class)} "
            f"{context_phrase(reason.context)}"
        )

    share = reason.share * 100
    shown = f"{share:.1f}%" if share >= 0.1 else "under 0.1%"
    plural = reason.records_sharing != 1
    return (
        f"{what} — on {reason.records_sharing:,} of {reason.total_records:,} "
        f"record{'s' if plural else ''} in this analysis ({shown})"
    )
