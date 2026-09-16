"""Public contract of the system module.

Owns no tables — status and configuration are assembled from PostgreSQL catalogs, the running
process and application settings. No other module depends on this one.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from time_reporting.core.cqrs import Command, Query

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
    last_backup_at: datetime | None


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
    backup_dir: str
    backup_retention_count: int
    backup_timeout_seconds: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BackupInfoDTO:
    name: str
    created_at: datetime
    # The alembic revision the database was at when the dump was taken; `None` only for a dump
    # made before the database had ever been migrated.
    revision: str | None
    size_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BackupListDTO:
    backups: tuple[BackupInfoDTO, ...]
    last_backup_at: datetime | None


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetSystemStatus(Query[SystemStatusDTO]):
    # The process start time, read from `app.state` by the router — not domain data this module
    # could otherwise obtain.
    started_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class GetSystemConfig(Query[SystemConfigDTO]):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ListBackups(Query[BackupListDTO]):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class GetBackupPath(Query[Path]):
    """Resolves a backup file name to its path on disk, for the download endpoint."""

    name: str


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBackup(Command[BackupInfoDTO | None]):
    # Used by `migrate` before applying pending migrations: only back up (and return non-`None`)
    # when the database has already been migrated at least once and isn't already at head.
    only_if_migrations_pending: bool = False
    # Only set for the "create backup now" API call; left `None` for the CLI (`time-reporting
    # backup`, whether run by hand or on the `backup`/`migrate` compose services' schedule), which
    # is also why only an API-triggered backup is audited (see `CreateBackupHandler`) — logging
    # every automatic scheduled backup would drown out real admin actions in the audit log.
    actor_id: UUID | None = None


# --- Exceptions ---


class SystemError(Exception):
    """Base class for system module domain errors."""


class BackupInProgressError(SystemError):
    def __init__(self) -> None:
        super().__init__("A backup is already in progress")


class BackupFailedError(SystemError):
    """`pg_dump`/`pg_restore` exited non-zero or timed out. The stderr tail is logged, never
    included here — it may contain connection details."""

    def __init__(self, message: str = "Backup failed; see server logs for details") -> None:
        super().__init__(message)


class BackupNotFoundError(SystemError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Backup {name!r} not found")
        self.name = name
