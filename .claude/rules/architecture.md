## Architecture

`Ingest (upload | OAuth 2.0) → Normalize → Dependency graph → Reasoning → Ranked factors → API → UI`

Key boundaries:

- `ingest/` — file upload parsing and NetSuite retrieval, behind one interface.
- `connector/` — OAuth 2.0 auth, REST, SuiteQL, rate limiting, read-only access.
- `evidence/` — raw evidence, normalized records, relationships, provenance.
- `graph/` — dependency graph across records, fields, scripts, workflows, integrations.
- `reasoning/` — contributing-factor ranking, evidence assembly, LLM integration.
- `api/` — application routes and orchestration.
- `frontend/` — consultant investigation interface.
- `tests/` — unit, integration, connector, reasoning, end-to-end.
- `config/` — configuration and environment definitions.

Keep NetSuite-specific logic inside `connector/` and `ingest/`. NetSuite response
shapes must not leak into the graph, reasoning, or frontend layers.
