# Tech Stack — NetSuite Transaction Impact Copilot

Decided 28 August 2026. Optimised for one part-time founder shipping something a
consultant can try, not for scale that does not exist yet.

## The stack

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12** | One language end to end. Boring, readable, already known. |
| Web framework | **FastAPI** | Async for NetSuite I/O, Pydantic validation built in, serves both HTML and JSON from one app. |
| UI | **Jinja2 + HTMX + Tailwind (CDN)** | No build step, no second language, no second deploy. A ranked-factor report is server-rendered content. |
| Validation / contracts | **Pydantic v2** | The typed interfaces `conventions.md` requires, and the schema LLM output is validated against. |
| Database | **PostgreSQL 16** | JSONB for raw evidence, relational for normalized records. One engine, both jobs. |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Explicit, mature, no surprises. |
| Graph | **NetworkX, in memory** | The dependency graph is per-analysis and small. A graph database is a solved problem you do not have yet. |
| HTTP client | **httpx** | Async, timeouts, retries, works with FastAPI. |
| Retry / backoff | **tenacity** | NetSuite 429 handling with `Retry-After`. |
| Background jobs | **arq** (Redis) | Analysis runs longer than a request. Lighter than Celery. Not needed until Path B. |
| LLM | **Claude API** (`anthropic` SDK) | Structured JSON output, long context for evidence bundles. |
| Auth (our users) | **Session cookies + `argon2`** | No third-party identity provider until a client asks for SSO. |
| Secrets | Environment variables → **Render/Fly secrets** | Never in the database in plaintext, never in the frontend. |
| Tests | **pytest + pytest-asyncio + respx** | `respx` mocks NetSuite HTTP so tests never need a live account. |
| Lint / types | **ruff + mypy** | One tool for lint and format. |
| Packaging | **uv** | Fast, lockfile-based, replaces pip/venv/poetry. |
| Container | **Docker** (single image) | Same artifact locally and in production. |
| Hosting | **Render** (or Fly.io) | Managed Postgres + Redis, container deploy, ~$20–40/mo, near-zero ops. |
| CI | **GitHub Actions** | ruff + mypy + pytest on push. |
| Error tracking | **Sentry** (free tier) | You will not be watching logs at 2am. |

## What is deliberately absent

- **No React / Next.js.** A second language and a second deploy for a report page.
  Revisit only if an interactive graph explorer becomes the thing people pay for.
- **No Neo4j / graph database.** NetworkX in process until a single analysis
  outgrows memory.
- **No Celery, Kafka, Kubernetes, microservices.** One process, one database.
- **No vector database.** Nothing here is a similarity search problem — it is a
  dependency-graph problem with an LLM explaining the result.
- **No multi-tenant sharding.** Tenant ID column and enforced filters are enough
  until there are tenants.

## Repository layout

```
maica/
  ingest/        upload parsers (CSV, XML, log) + NetSuite retrieval, one interface
  connector/     OAuth 2.0, REST, SuiteQL, rate limiting, read-only
  evidence/      raw store, normalizer, provenance
  graph/         dependency graph construction
  reasoning/     factor ranking, evidence assembly, LLM client + schemas
  api/           FastAPI routes and orchestration
  web/           Jinja templates, HTMX partials, static
  config/        settings, environments
tests/           unit, integration, connector (respx), reasoning, e2e
docs/
migrations/      Alembic
```

## Data model sketch

- `tenants` — one per client account.
- `analyses` — one investigation; status, tenant, created_by.
- `raw_evidence` — JSONB payload, source type, fetched/uploaded at, request made,
  what was returned, what was unavailable. Never mutated.
- `records` — normalized rows: `source_id`, `record_type`, `field_name`,
  `old_value`, `new_value`, `actor`, `occurred_at`, `raw_evidence_id`.
- `factors` — ranked contributing factors: label
  (`CONFIRMED` / `LIKELY` / `UNCERTAIN` / `INSUFFICIENT_EVIDENCE`), rank, summary,
  and the record IDs supporting it.
- `gaps` — what could not be checked, and why. First-class, not a log line.

Every factor joins back to records, which join back to raw evidence. That is the
provenance rule in `data-rules.md`, enforced by foreign keys rather than discipline.

## NetSuite constraints the connector must respect

Verified against Oracle documentation and current governance write-ups:

- **OAuth 2.0 authorization code flow** requires an integration record created by an
  administrator (or a holder of the Integration Application permission) and an
  application able to open a browser. Client ID and secret are shown once.
- **Access token lifetime: 3600 seconds.** Refresh transparently; never let a token
  refresh surface to the user as an error.
- **Refresh token lifetime is not stated in Oracle's token-structure documentation.**
  Commonly reported as seven days for this flow — treat as **unverified** and design
  for silent re-consent rather than assuming a number.
- **Concurrency is account-wide** across REST, SOAP and RESTlets: 5 on Standard,
  15 Premium, 20 Enterprise/Ultimate, +10 per SuiteCloud Plus license. Developer
  accounts are capped at 5. We share this pool with the client's own integrations —
  which is the practical reason `connector-rules.md` forbids speculative polling.
- **SuiteQL: 1,000 rows per page** (REST defaults to 100), 100,000 rows per query.
  Paginate explicitly.
- **HTTP 429** on frequency limits, with `Retry-After`. Exponential backoff via
  tenacity, and surface throttling as a named gap rather than a silent truncation.

## Build order

1. **Path A skeleton** — FastAPI app, upload endpoint, one parser (saved search
   CSV), raw evidence stored with provenance. No LLM, no graph.
2. **Normalizer + records** — one export becomes typed rows with source IDs.
3. **Dependency graph** — build it from records; render it as text before HTML.
4. **Reasoning v0** — deterministic ranking rules only, no LLM. Prove the shape of
   the output is useful.
5. **LLM layer** — Claude explains the ranked factors, schema-validated, citing
   record IDs. Reject anything uncited.
6. **UI** — the report page, the gaps section, the next-step suggestion.
7. **Path B connector** — OAuth 2.0 script first: authenticate, pull one real
   transaction, try to trace it. This is the current next step.

Steps 1–6 need no NetSuite account at all. That is the point of upload-first.

## Open decisions

- Hosting region — pick when the first pilot client's data residency is known.
- Whether `arq` + Redis is needed before Path B. Probably not.
