# CLAUDE.md — NetSuite Transaction Impact Copilot

## What this is

A read-only diagnostic tool for NetSuite. When a transaction posts wrong, it reads
the account and returns a **ranked map of contributing factors** — not a single
answer. The consultant decides; the tool shows them where to look.

The value sits in the gap between two people:

- **Functional consultants** see configuration, not code.
- **Technical consultants** see code, not configuration.

The expensive bugs live exactly between them — a script firing on a record whose
config changed months ago. Neither specialist can see the other half. That gap is
the product.

## Who buys it

| Role | Who |
|---|---|
| **Pays** | The end client (company running NetSuite) or the consulting firm |
| **Champions it** | The NetSuite consultant — recommends and uses it |
| **Feels the pain** | NetSuite Administrator, Controller, Finance Manager |

**The consultant is never the payer.** Confirmed by three consultants independently.
If an hourly consultant saves time, the client captures the benefit — so the client
pays. Do not design self-serve consumer pricing for this.

## Settled decisions — do not re-litigate

- **Auth: OAuth 2.0 authorization code flow.** Not TBA (OAuth 1.0a), which was the
  original plan. Consultants reached for OAuth 2.0 unprompted. Browser consent means
  we never hold their credentials — a materially better security story for a
  production ERP.
- **Read-only, always.** Never write to a client ledger. "We cannot modify anything
  in your account" is the strongest sentence available in a security conversation.
- **Integration record** can be created by an administrator *or* a holder of the
  Integration Application permission. Client ID and secret are shown **once only** at
  creation — capture immediately.
- **Client data may go into the tool** with client approval. Precedent exists: one
  consultant's team already runs client NetSuite data through Claude via a connector.
- **Never poll speculatively.** NetSuite meters API usage per account. Throttling
  annoys the client's admin — the exact person whose goodwill onboarding depends on.
  Pull on demand, cache aggressively.

## Two ingestion paths, one engine

**Path A — upload first (v1).** Consultant exports what they already see (saved
search CSV, script deployment list, workflow definition, execution log) and uploads
it. No admin, no integration record, no IT ticket. This is the wedge — someone can
try it in five minutes.

**Path B — live connection (v2).** OAuth 2.0 against the client account. Sold as the
upgrade after someone already wants it.

Both feed the same engine: normalize → dependency graph → reason → ranked factors.
Ingestion is plumbing; the engine is the product.

## Open questions

1. **Does the analysis generalise?** Target accounts are heavily customised — custom
   records, custom fields, bespoke scripts, all different per account. If reasoning
   only works on hand-tuned accounts, this is consulting with extra steps. **Only
   building answers this.**
2. **Will anyone actually pay?** The payer is identified; payment is unproven. Needs
   a call with a client, not a consultant.

## Working rules for Claude

- Prefer Python. Solo founder, part-time, night shift — favour boring, readable code
  over clever architecture.
- Degrade gracefully on partial access: analyse what is readable and state plainly
  which inputs were missing. A diagnostic that names its blind spots is more
  trustworthy, not less.
- Never invent NetSuite API behaviour. Verify against docs.oracle.com or say it is
  unverified.
- Keep responses short and plain. Long dense answers with many tables are
  overwhelming — lead with the key point and stop.

## Status

Research phase is closed. Access, auth, permission and buyer questions are all
answered. Next step is the OAuth 2.0 connection script: authenticate, pull one real
transaction, try to trace it.

_Last updated 28 August 2026._

## Phase A — Beta polish (current focus)

Steps 1-6 of the build order are built and working end to end (upload → normalize
→ graph → reasoning v0 → LLM explanation → report UI), but this is being treated
as a **Beta**, not a finished Phase A. Phase B (the OAuth 2.0 connector) is
deliberately on hold until Phase A is fully built out — do not start Path B work
without an explicit decision to do so.

Remaining Phase A work, in rough priority order:
1. More upload parsers (script deployment list, workflow definition, execution
   log) — the current reasoning output is thin because it only has transaction
   snapshots to work with.
2. Real LLM verification with a configured `ANTHROPIC_API_KEY` — narration has
   only been proven via its fallback path so far.
3. Real app login (session cookies + argon2, per the decided stack) replacing the
   dev-only `X-Tenant-Id` header.
4. A dashboard/home page listing analyses for a tenant.
5. UI polish and broader test coverage with messier real-world-shaped exports.
6. Git remote + CI verification; Docker build verification once available.

## Rules

@rules/product.md
@rules/ingestion.md
@rules/architecture.md
@rules/auth-rules.md
@rules/connector-rules.md
@rules/data-rules.md
@rules/reasoning-rules.md
@rules/llm-rules.md
@rules/security.md
@rules/conventions.md
@rules/commands.md
@rules/workflow.md
@rules/hard-rules.md
@rules/tools-notes.md
