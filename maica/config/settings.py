from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://maica:maica@localhost:5432/maica"
    environment: str = "development"
    anthropic_api_key: str | None = None
    llm_model: str = "claude-haiku-4-5-20251001"
    # Signs the session cookie. Must be overridden via env var outside development —
    # anyone with this value can forge a session.
    session_secret_key: str = "dev-insecure-secret-change-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
