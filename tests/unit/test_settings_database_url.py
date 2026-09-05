"""The database URL a hosting provider hands out.

Render and Neon supply "postgresql://...", Heroku-style hosts "postgres://".
SQLAlchemy treats the scheme as the driver name, so both select psycopg2 —
which this app does not install. Pasting the provider's string in unedited has
to work, or the first deploy fails on a missing module and reads like a broken
build rather than a configuration mismatch.
"""

import pytest

from maica.config.settings import Settings


@pytest.mark.parametrize(
    "supplied",
    [
        "postgresql://maica:pw@db.internal:5432/maica",
        "postgres://maica:pw@db.internal:5432/maica",
    ],
    ids=["render-and-neon", "heroku-style"],
)
def test_a_providers_connection_string_gets_the_async_driver(supplied: str) -> None:
    settings = Settings(database_url=supplied)

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.database_url.endswith("@db.internal:5432/maica")


def test_an_explicit_driver_is_left_alone() -> None:
    explicit = "postgresql+asyncpg://maica:pw@localhost:5432/maica"

    assert Settings(database_url=explicit).database_url == explicit


def test_the_password_is_not_mangled_by_the_rewrite() -> None:
    # The rewrite is a prefix swap, so anything that looks like the scheme
    # inside the credentials must survive it.
    settings = Settings(database_url="postgresql://u:postgres://x@h:5432/d")

    assert settings.database_url == "postgresql+asyncpg://u:postgres://x@h:5432/d"
