"""Application settings loaded from environment variables and an optional ``.env`` file."""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, SecretStr
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

    # Signs and verifies JWT access tokens; generate with `openssl rand -hex 32`.
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # Browsers send `Secure` cookies only over HTTPS and to http://localhost; disable only when the
    # web client is served over plain HTTP from another host.
    auth_cookie_secure: bool = True

    # ISO 3166-1 alpha-2 country (and optional subdivision, e.g. a German state) whose public
    # holidays `ImportPublicHolidays` copies from the `holidays` library into the shared calendar.
    holiday_country: str = "DE"
    holiday_subdivision: str | None = None

    # Hours a full working day counts as, for the "expected hours" shown against reported time on
    # the employee dashboard (`timesheets.summary`). Not enforced anywhere — a user may report more
    # or less on any given day.
    daily_working_hours: Decimal = Field(default=Decimal("8"), gt=0, le=24)


@lru_cache
def get_settings() -> Settings:
    return Settings()
