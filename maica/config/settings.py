from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

#: The value shipped in .env.example. Anyone with it can forge a session cookie
#: for any user, so the app refuses to start outside development while it is set.
INSECURE_SESSION_KEY = "dev-insecure-secret-change-in-production"


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
    # Ollama defaults num_ctx to a few thousand tokens regardless of what the model
    # supports, and silently truncates anything longer. A truncated evidence bundle
    # made the model state that a record was absent when it was in the prompt — the
    # worst failure this tool can have, so the window is always set explicitly.
    llm_context_tokens: int = 16384
    # Signs the session cookie. Must be overridden via env var outside development —
    # anyone with this value can forge a session.
    session_secret_key: str = INSECURE_SESSION_KEY
    # Google OAuth (the only sign-in method). None until set — callers must
    # degrade gracefully (hide the sign-in option) rather than treat a
    # missing value as an error.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://127.0.0.1:8000/auth/google/callback"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def session_key_is_insecure(self) -> bool:
        return self.session_secret_key == INSECURE_SESSION_KEY


@lru_cache
def get_settings() -> Settings:
    return Settings()
