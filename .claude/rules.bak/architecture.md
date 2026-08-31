## Architecture

The system follows:

`NetSuite → Connector → Evidence Store → Normalizer → Timeline → Impact Analysis → LLM → API → UI`

Key boundaries:

- `connector/` — read-only NetSuite authentication, REST, SuiteQL, and data retrieval.
- `backend/` — API routes, authentication, orchestration, and application services.
- `evidence/` — raw evidence, normalized records, relationships, provenance, and timelines.
- `reasoning/` — transaction impact analysis, causal-chain generation, validation, and LLM integration.
- `frontend/` — consultant investigation interface.
- `tests/` — unit, integration, connector, reasoning, and end-to-end tests.
- `config/` — application configuration and environment definitions.

Keep NetSuite-specific logic inside `connector/`. Do not leak NetSuite response formats into the reasoning or frontend layers.
