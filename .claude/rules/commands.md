## Commands

Stack: Python 3.12 · FastAPI · Jinja2 + HTMX · PostgreSQL 16 · SQLAlchemy 2.0 ·
Claude API · uv · Docker · Render. Full rationale in `docs/tech-stack.md`.

- Install: `uv sync`
- Dev: `uv run uvicorn maica.api.main:app --reload`
- Test: `uv run pytest`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- Typecheck: `uv run mypy maica`
- Migrations: `uv run alembic upgrade head` / `uv run alembic revision --autogenerate -m "..."`
- Build: `docker build -t maica .`

Run lint, typecheck and tests before finishing any change. Never invent a command
that is not listed here — add it here first.
