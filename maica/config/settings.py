from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://maica:maica@localhost:5432/maica"
    environment: str = "development"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    # A local model serves one request at a time, so a chat question asked while a
    # report is still narrating its factors queues behind them. 60s was too tight
    # for that and surfaced as a spurious 'could not be reached'.
    llm_timeout_seconds: float = 180.0
    # Signs the session cookie. Must be overridden via env var outside development —
    # anyone with this value can forge a session.
    session_secret_key: str = "dev-insecure-secret-change-in-production"
    # Google OAuth (the only sign-in method). None until set — callers must
    # degrade gracefully (hide the sign-in option) rather than treat a
    # missing value as an error.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://127.0.0.1:8000/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
