# Labelled scenarios

Six datasets where the answer was planted on purpose, so accuracy is a number
rather than an opinion. `ground_truth.json` records, for each one, which
records are affected and what was put there to separate them from the rest.

```
uv run python test-dataset/scenarios/generate_scenarios.py   # rebuild the CSVs
uv run python test-dataset/scenarios/evaluate.py             # score the engine
uv run pytest tests/integration/test_scenario_accuracy.py    # same, as a guard
```

Each is ~300 records with 900-1,200 change rows. Every record carries 2-4
background changes drawn from one pool for both cohorts, so the noise cannot
separate them by accident — only the planted signal can.

| Scenario | What was planted | Expected |
|---|---|---|
| `clean_automated_cause` | A scheduled process changed Account on all 40 affected and no others | `ONLY IN AFFECTED` |
| `skipped_approval` | All 260 unaffected went through an approval workflow; none of the affected did | `ABSENT FROM AFFECTED` |
| `partial_cause` | A process hit ~80% of affected and ~6% of the rest — the ordinary, messy case | `MORE COMMON IN AFFECTED` |
| `confounded` | A rare real cause, plus a Status change on all 300 records in both cohorts | `ONLY IN AFFECTED`, and Status must not rank at all |
| `nothing_to_find` | Nothing. Both cohorts drawn from one distribution | No finding |
| `too_few_affected` | A perfect separator, but on only 2 records | `TOO FEW RECORDS TO TELL` |

## Result

**6/6.** Verified rendering rather than inferred: `nothing_to_find` returns
zero findings and the headline *"Nothing in this evidence separates the 40
affected records from the other 260"*, and `confounded` ranks Subsidiary at
40/40 vs 0/260 while excluding Status entirely.

`nothing_to_find` is the one worth protecting. A diagnostic that always finds
something is worse than one that finds nothing, because the consultant cannot
tell the two apart.

## What this does and does not establish

It establishes that the comparison finds a planted difference in four shapes,
declines to invent one when there is none, and refuses to conclude from two
records.

It does not establish that a real NetSuite account's problems look like these
shapes. The data is synthetic and the noise is uniform, which is kinder than
reality in one respect — a real account's background is lumpy, and a genuine
cause can hide inside a pattern that is already common. That needs a real
export to answer.
