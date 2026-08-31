from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://maica:maica@localhost:5432/maica"
    environment: str = "development"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    # Signs the session cookie. Must be overridden via env var outside development —
    # anyone with this value can forge a session.
    session_secret_key: str = "dev-insecure-secret-change-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
