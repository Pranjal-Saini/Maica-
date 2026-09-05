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

# Bind whatever the host asks for, falling back to 8000 for local runs. Render
# sets PORT (10000 by default) and only "usually" manages to detect a service
# listening somewhere else — a hardcoded port fails the port scan and the
# deploy dies with no open ports detected.
#
# sh -c is needed because the exec form does not expand variables, and the
# leading exec hands PID 1 to the server so SIGTERM reaches it and shutdown
# stays graceful instead of waiting to be killed.
CMD ["sh", "-c", "exec uv run uvicorn maica.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
