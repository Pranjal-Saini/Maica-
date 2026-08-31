## Ingestion Rules

Two paths, one engine. Ingestion is plumbing; the engine is the product.

**Path A — upload first (v1, the wedge)**

- Accept what a consultant can already export without admin rights: saved search
  CSV, script deployment lists, workflow definitions, execution logs.
- No admin, no integration record, no IT ticket. Someone must be able to try it in
  five minutes.
- Treat every uploaded file as untrusted input. Validate structure before parsing.
- Tolerate messy exports: extra columns, renamed headers, partial date ranges.
  Report what was understood and what was skipped.

**Path B — live connection (v2)**

- OAuth 2.0 against the client account, sold as the upgrade after someone already
  wants it.

Both paths must normalize into the same internal record shape. No reasoning code
may branch on which path the evidence arrived through.
