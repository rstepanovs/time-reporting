"""Public contract of the system module.

Owns no tables — status and configuration are assembled from PostgreSQL catalogs, the running
process and application settings. No other module depends on this one.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from time_reporting.core.cqrs import Query

# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class TableStatsDTO:
    name: str
    estimated_rows: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DatabaseStatusDTO:
    server_version: str
    size_bytes: int
    connection_count: int
    # From the `alembic_version` table and the running code's migration scripts, respectively;
    # a mismatch means the database hasn't been migrated to what this backend expects.
    current_revision: str | None
    head_revision: str | None
    migrations_pending: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemStatusDTO:
    backend_version: str
    git_sha: str | None
    database: DatabaseStatusDTO
    tables: tuple[TableStatsDTO, ...]
    started_at: datetime
    uptime_seconds: float


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemConfigDTO:
    """A deliberate whitelist of non-secret settings — never `jwt_secret_key` or the DB password."""

    app_name: str
    debug: bool
    cors_origins: tuple[str, ...]
    access_token_expire_minutes: int
    auth_cookie_secure: bool
    holiday_country: str
    holiday_subdivision: str | None
    daily_working_hours: Decimal


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetSystemStatus(Query[SystemStatusDTO]):
    # The process start time, read from `app.state` by the router — not domain data this module
    # could otherwise obtain.
    started_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class GetSystemConfig(Query[SystemConfigDTO]):
    pass
