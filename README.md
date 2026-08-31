# MAICA — NetSuite Transaction Impact Copilot

Read-only diagnostic tool for NetSuite. Ingests evidence about an account and
returns a ranked map of contributing factors for why a transaction posted
wrong — the consultant decides, the tool shows the evidence.

Path A (upload-first, no NetSuite account needed) is built end to end: upload
→ normalize → dependency graph → deterministic reasoning → LLM explanation →
report UI, behind real login. This is a Beta — see `.claude/claude.md` for
what's still being polished before Phase B (the OAuth 2.0 connector).

## Quickstart

```
uv sync
docker compose up -d db      # or use a local PostgreSQL 16 instance
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn maica.api.main:app --reload
```

Visit http://127.0.0.1:8000/signup, create an account, add a client account
from the dashboard, then upload a saved-search CSV or System Notes export.

Set `ANTHROPIC_API_KEY` in `.env` to enable real LLM narration of ranked
factors — without it, the app falls back to the rule-based summaries and says
so explicitly. Set `SESSION_SECRET_KEY` to anything other than the dev
default before deploying anywhere other than your own machine.

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
