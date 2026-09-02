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

Uploading files 1-3 together gives record 4471 **eight ranked factors**, all
`UNCERTAIN`: four field changes (memo, account, status, amount) and four
shared-value correlations (account, status, entity). The `System` actor is
described as "an automated process, not a specific person", and nothing is
called a cause. That restraint is the product.

### A known weakness this data exposes

The **memo** change ranks #1, above the account reclassification — so "next
thing worth looking at" points at a memo being filled in, which is the least
interesting event on the record. Ranking currently weighs recency and evidence
type but not *which field* changed. A mis-posting is about the account, and the
ranking does not know that yet.

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
