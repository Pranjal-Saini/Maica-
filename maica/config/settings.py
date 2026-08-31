from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://maica:maica@localhost:5432/maica"
    environment: str = "development"
    dev_tenant_id: UUID = UUID("00000000-0000-0000-0000-000000000001")


@lru_cache
def get_settings() -> Settings:
    return Settings()
