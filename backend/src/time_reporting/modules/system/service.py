"""Assembles system status/config from the repository's catalog queries, application settings and
Alembic's script directory."""

from datetime import UTC, datetime
from importlib.metadata import version

from alembic.config import Config
from alembic.script import ScriptDirectory

from time_reporting.core.config import Settings, get_settings
from time_reporting.modules.system.contracts import (
    DatabaseStatusDTO,
    SystemConfigDTO,
    SystemStatusDTO,
)
from time_reporting.modules.system.repository import SystemRepository

_BACKEND_DISTRIBUTION = "time-reporting-backend"


class SystemService:
    def __init__(self, repository: SystemRepository) -> None:
        self._repository = repository

    async def get_status(self, *, started_at: datetime) -> SystemStatusDTO:
        settings = get_settings()
        current_revision = await self._repository.get_current_revision()
        head_revision = _get_head_revision(settings.alembic_config_path)
        database = DatabaseStatusDTO(
            server_version=await self._repository.get_server_version(),
            size_bytes=await self._repository.get_database_size(),
            connection_count=await self._repository.get_connection_count(),
            current_revision=current_revision,
            head_revision=head_revision,
            migrations_pending=current_revision != head_revision,
        )
        return SystemStatusDTO(
            backend_version=version(_BACKEND_DISTRIBUTION),
            git_sha=settings.app_git_sha,
            database=database,
            tables=await self._repository.get_table_stats(),
            started_at=started_at,
            uptime_seconds=(datetime.now(UTC) - started_at).total_seconds(),
        )

    async def get_config(self) -> SystemConfigDTO:
        return _config_dto(get_settings())


def _get_head_revision(alembic_config_path: str) -> str | None:
    config = Config(alembic_config_path)
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def _config_dto(settings: Settings) -> SystemConfigDTO:
    return SystemConfigDTO(
        app_name=settings.app_name,
        debug=settings.debug,
        cors_origins=tuple(settings.cors_origins),
        access_token_expire_minutes=settings.access_token_expire_minutes,
        auth_cookie_secure=settings.auth_cookie_secure,
        holiday_country=settings.holiday_country,
        holiday_subdivision=settings.holiday_subdivision,
        daily_working_hours=settings.daily_working_hours,
    )
