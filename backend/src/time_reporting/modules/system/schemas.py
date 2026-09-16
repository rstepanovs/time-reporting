"""HTTP response models of the system API."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TableStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    estimated_rows: int


class DatabaseStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    server_version: str
    size_bytes: int
    connection_count: int
    current_revision: str | None
    head_revision: str | None
    migrations_pending: bool


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    backend_version: str
    git_sha: str | None
    database: DatabaseStatusResponse
    tables: list[TableStatsResponse]
    started_at: datetime
    uptime_seconds: float
    last_backup_at: datetime | None


class SystemConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    app_name: str
    debug: bool
    cors_origins: list[str]
    access_token_expire_minutes: int
    auth_cookie_secure: bool
    holiday_country: str
    holiday_subdivision: str | None
    daily_working_hours: Decimal
    backup_dir: str
    backup_retention_count: int
    backup_timeout_seconds: int


class BackupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    created_at: datetime
    revision: str | None
    size_bytes: int


class BackupListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    backups: list[BackupResponse]
    last_backup_at: datetime | None
