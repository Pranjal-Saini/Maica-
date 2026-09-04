FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# The venv is already synced (production deps only) at build time; without
# this, `uv run` re-syncs at container start and pulls in the dev group
# (mypy, ruff, ...) that --no-dev deliberately excluded.
ENV UV_NO_SYNC=1

COPY maica ./maica
COPY migrations ./migrations
COPY alembic.ini ./

# Drop root before running. A container process that only reads uploads and
# talks to Postgres has no reason to be able to write the image, and it limits
# what a parser bug in untrusted CSV can reach.
RUN useradd --create-home --uid 10001 maica && chown -R maica:maica /app
USER maica

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "maica.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
