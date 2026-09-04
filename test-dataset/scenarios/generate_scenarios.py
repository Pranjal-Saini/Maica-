"""Scenarios with a known answer, for measuring whether the engine finds it.

Every other dataset here is realistic but unlabelled — you can look at the
output and judge it, but you cannot score it. These six carry ground truth: for
each one, which records are affected and what was planted as the difference
between them and the rest. That makes accuracy a number rather than an opinion.

Three of them plant a real cause in different shapes, one plants a confounder
alongside a real cause, one plants nothing at all, and one gives too few
affected records to conclude from. The scenario that plants nothing is the
important one: a diagnostic that always finds something is worse than useless,
so the engine has to be able to say there is nothing here.

    uv run python test-dataset/scenarios/generate_scenarios.py

Writes the CSVs plus ground_truth.json beside this file. Deterministic — the
seed is fixed, so a change in the score traces to a change in the code.
"""

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20260904
OUT = Path(__file__).parent

HEADER = [
    "Internal ID",
    "Record Type",
    "Date",
    "Field",
    "Old Value",
    "New Value",
    "Set By",
    "Context",
    "Type",
]

USERS = ["jsmith", "mchen", "alopez", "dpatel", "kowusu"]
#: The background hum every record has some of. Drawn from one pool for both
#: cohorts, so nothing here can separate them by accident.
NOISE_FIELDS = ["Memo", "Terms", "Class", "Department", "Location"]

START = datetime(2026, 7, 1, 9, 0)


def _row(rng, source_id, field, actor, context, when, old="a", new="b"):
    return [
        source_id,
        "Invoice",
        when.strftime("%m/%d/%Y %H:%M"),
        field,
        old,
        new,
        actor,
        context,
        "Change",
    ]


def _noise(rng, source_id, when):
    rows = []
    for field in rng.sample(NOISE_FIELDS, rng.randint(2, 4)):
        rows.append(
            _row(
                rng,
                source_id,
                field,
                rng.choice(USERS),
                "UI",
                when + timedelta(minutes=rng.randint(1, 400)),
            )
        )
    return rows


def _build(rng, total, affected_count, plant):
    """plant(rng, source_id, is_affected, when) -> extra rows."""
    ids = [f"{7000 + i}" for i in range(total)]
    affected = set(ids[:affected_count])
    rows = []
    for index, source_id in enumerate(ids):
        when = START + timedelta(minutes=index * 7)
        rows.extend(_noise(rng, source_id, when))
        rows.extend(plant(rng, source_id, source_id in affected, when))
    rng.shuffle(rows)
    return rows, sorted(affected)


def scenario_clean_automated_cause(rng):
    """One scheduled process touched every affected record and nothing else."""

    def plant(rng, source_id, is_affected, when):
        if is_affected:
            return [_row(rng, source_id, "Account", "System", "SCHEDULED", when, "4000", "4010")]
        return []

    rows, affected = _build(rng, 300, 40, plant)
    return (
        rows,
        affected,
        {
            "expect": "ONLY IN AFFECTED",
            "field": "Account",
            "actor_class": "System",
            "context": "SCHEDULED",
            "why": "planted on all 40 affected records and no others",
        },
    )


def scenario_skipped_approval(rng):
    """The affected records never went through a step everything else did."""

    def plant(rng, source_id, is_affected, when):
        if not is_affected:
            return [
                _row(
                    rng,
                    source_id,
                    "Approval",
                    rng.choice(USERS),
                    "WORKFLOW",
                    when,
                    "Pending",
                    "Signed",
                )
            ]
        return []

    rows, affected = _build(rng, 300, 40, plant)
    return (
        rows,
        affected,
        {
            "expect": "ABSENT FROM AFFECTED",
            "field": "Approval",
            "actor_class": "user",
            "context": "WORKFLOW",
            "why": "planted on all 260 unaffected records and none of the affected",
        },
    )


def scenario_partial_cause(rng):
    """A real cause that is neither universal among the affected nor absent
    outside them — the ordinary, messy case."""

    def plant(rng, source_id, is_affected, when):
        hit = rng.random() < (0.8 if is_affected else 0.06)
        if hit:
            return [_row(rng, source_id, "Amount", "System", "USEREVENT", when, "100.00", "150.00")]
        return []

    rows, affected = _build(rng, 300, 50, plant)
    return (
        rows,
        affected,
        {
            "expect": "MORE COMMON IN AFFECTED",
            "field": "Amount",
            "actor_class": "System",
            "context": "USEREVENT",
            "why": "planted on ~80% of affected and ~6% of the rest",
        },
    )


def scenario_confounded(rng):
    """A very common change sits in both cohorts alongside a rare real cause.
    The common one must not outrank the real one."""

    def plant(rng, source_id, is_affected, when):
        rows = [_row(rng, source_id, "Status", rng.choice(USERS), "UI", when, "Open", "Approved")]
        if is_affected:
            rows.append(_row(rng, source_id, "Subsidiary", "System", "WORKFLOW", when, "UK", "DE"))
        return rows

    rows, affected = _build(rng, 300, 40, plant)
    return (
        rows,
        affected,
        {
            "expect": "ONLY IN AFFECTED",
            "field": "Subsidiary",
            "actor_class": "System",
            "context": "WORKFLOW",
            "why": "Status is on every record in both cohorts and must not win",
            "must_not_rank_first": "Status",
        },
    )


def scenario_nothing_to_find(rng):
    """Nothing distinguishes the two groups. The engine must say so rather
    than promoting noise — the false-positive test, and the one that matters
    most for trust."""

    def plant(rng, source_id, is_affected, when):
        # Identical distribution for both cohorts.
        return [_row(rng, source_id, "Amount", rng.choice(USERS), "UI", when, "10.00", "20.00")]

    rows, affected = _build(rng, 300, 40, plant)
    return (
        rows,
        affected,
        {
            "expect": "NOTHING",
            "why": "affected and unaffected were generated from the same distribution",
        },
    )


def scenario_too_few_affected(rng):
    """A perfect separator, but only two affected records. Two agreeing is not
    evidence, and the engine has to say that instead of ranking it."""

    def plant(rng, source_id, is_affected, when):
        if is_affected:
            return [_row(rng, source_id, "Account", "System", "SCHEDULED", when, "4000", "4010")]
        return []

    rows, affected = _build(rng, 300, 2, plant)
    return (
        rows,
        affected,
        {
            "expect": "TOO FEW RECORDS TO TELL",
            "field": "Account",
            "why": "a perfect separation on only 2 records is not yet evidence",
        },
    )


SCENARIOS = {
    "clean_automated_cause": scenario_clean_automated_cause,
    "skipped_approval": scenario_skipped_approval,
    "partial_cause": scenario_partial_cause,
    "confounded": scenario_confounded,
    "nothing_to_find": scenario_nothing_to_find,
    "too_few_affected": scenario_too_few_affected,
}


def main() -> None:
    rng = random.Random(SEED)
    truth = {}
    for name, build in SCENARIOS.items():
        rows, affected, expected = build(rng)
        path = OUT / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(rows)
        truth[name] = {"affected_ids": affected, "change_rows": len(rows), **expected}
        print(f"{name:26} {len(rows):>5} change rows, {len(affected):>3} affected -> {path.name}")

    (OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"\nground truth -> {(OUT / 'ground_truth.json').name}")


if __name__ == "__main__":
    main()
