"""Application settings loaded from environment variables and an optional ``.env`` file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Time Reporting"
    debug: bool = False

    database_url: str = (
        "postgresql+asyncpg://time_reporting:time_reporting@localhost:5432/time_reporting"
    )
    database_echo: bool = False

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
