# Test dataset

Synthetic NetSuite-shaped exports for trying MAICA end to end. No real client
data — invented companies, invented internal IDs.

Upload them together (the type of each file is detected from its own headers)
against any client account, then open record **4471**.

| File | What it is | Why it's here |
|---|---|---|
| `1_transactions_saved_search.csv` | Saved-search export, 8 transactions | The snapshot: amounts, accounts, entities |
| `2_system_notes.csv` | System Notes export, 13 field changes | The audit trail: who changed what, from what, in what context |
| `3_transactions_messy.csv` | A deliberately awkward saved search | Proves the parser degrades gracefully instead of failing |
| `4_not_a_netsuite_export.csv` | An HR spreadsheet | Proves an unrecognised file is reported, not guessed at |

## The story in the data

Invoice **4471** is the one that posted wrong. Two things happened to it within
a minute of each other on 12 July:

- `jsmith` raised the amount from 15,000.00 to 18,400.00 from the UI.
- Something running as `System` in a `SCHEDULED` context moved it from
  `4000 - Product Revenue` to `4010 - Service Revenue`, then approved it.

The same `System` account reclassification also hit **4472** and **4473**.
Journal **4475** reverses 4471's exact amount into deferred revenue, and credit
memo **4477** credits it back in part.

Uploading files 1-3 together gives record 4471 **eight ranked factors**:

| Rank | Label | Factor |
|---|---|---|
| 1 | `CONFIRMED` | Account changed 4000 → 4010 by `System`, context `SCHEDULED` |
| 2 | `CONFIRMED` | Status changed Pending Approval → Approved by `System` |
| 3 | `CONFIRMED` | Amount changed 15,000 → 18,400 by `jsmith` |
| 4 | `CONFIRMED` | Memo first set (populated, not altered — so ranked below the three above) |
| 5-7 | `UNCERTAIN` | Account, Status and entity values shared with 2-4 other records |
| 8 | `INSUFFICIENT_EVIDENCE` | Account shared with 6 records — routine, isolates nothing |

`CONFIRMED` means the **change** is proven by the audit trail, never that it
caused the outcome — each summary says so explicitly, and every factor carries
the underlying rows (field, from, to, actor, context, timestamp) so the
consultant can check it in NetSuite. The `System` actor is described as "an
automated process, not a specific person". That restraint is the product.

### A known limitation this data exposes

Ordering uses whether an existing value was altered, then recency. It does
**not** weight fields by importance — nothing tells it an account matters more
than a status for a mis-posting. That is a NetSuite domain judgement with no
verified basis in the code yet, so the consultant makes it from the ranked
list. Here it happens to come out right; on another account it may not.

## What each awkward row in file 3 is for

Uploaded on its own, file 3 yields **4 rows understood, 1 skipped, 3 columns
ignored**.

| Row | What it exercises |
|---|---|
| Renamed headers (`InternalID`, `Transaction Date`, `Entity`) | Header aliasing |
| Extra columns (`Subsidiary`, `Currency`, `Approval Status`) | Unknown columns tolerated, reported as ignored |
| A blank line | Skipped without stopping the parse |
| `Ghost Row Ltd` with no Internal ID | Dropped — untraceable back to NetSuite — and counted in "rows skipped" |
| `4481` with a blank amount | Missing value represented, never guessed |
| `4482` with `not a date` | Unparseable date kept as unavailable rather than invented |

The upload result reports rows understood, rows skipped, and columns ignored
for every file, so all of the above should be visible rather than silent.
