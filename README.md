# MAICA — NetSuite Transaction Impact Copilot

Read-only diagnostic tool for NetSuite. Ingests evidence about an account and
returns a ranked map of contributing factors for why a transaction posted
wrong — the consultant decides, the tool shows the evidence.

This is Step 1 of the build order (`docs/tech-stack.md`): the Path A upload
skeleton. No graph, no reasoning, no LLM, no real UI yet — just a working,
tested, provenance-preserving upload pipeline.

## Quickstart

```
uv sync
docker compose up -d db      # or use a local PostgreSQL 16 instance
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn maica.api.main:app --reload
```

Visit http://127.0.0.1:8000/uploads/new and upload a saved-search CSV export.

## Commands

- Install: `uv sync`
- Dev: `uv run uvicorn maica.api.main:app --reload`
- Test: `uv run pytest`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- Typecheck: `uv run mypy maica`
- Migrations: `uv run alembic upgrade head` / `uv run alembic revision --autogenerate -m "..."`
- Build: `docker build -t maica .`

## Layout

See `docs/tech-stack.md` for the full repository layout and build order.
