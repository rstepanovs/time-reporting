"""Command and query handlers of the system module (registered in ``system.module``)."""

from pathlib import Path

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.system.backup_service import BackupService
from time_reporting.modules.system.contracts import (
    BackupInfoDTO,
    BackupListDTO,
    CreateBackup,
    GetBackupPath,
    GetSystemConfig,
    GetSystemStatus,
    ListBackups,
    SystemConfigDTO,
    SystemStatusDTO,
)
from time_reporting.modules.system.repository import SystemRepository
from time_reporting.modules.system.service import SystemService, get_head_revision


class _Handler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._repository = SystemRepository(bus.session)
        self._service = SystemService(self._repository)
        self._backup_service = BackupService(get_settings())


# --- Queries ---


class GetSystemStatusHandler(_Handler):
    async def handle(self, query: GetSystemStatus) -> SystemStatusDTO:
        return await self._service.get_status(
            started_at=query.started_at,
            last_backup_at=self._backup_service.last_backup_at(),
        )


class GetSystemConfigHandler(_Handler):
    async def handle(self, query: GetSystemConfig) -> SystemConfigDTO:
        return await self._service.get_config()


class ListBackupsHandler(_Handler):
    async def handle(self, query: ListBackups) -> BackupListDTO:
        backups = self._backup_service.list()
        return BackupListDTO(backups=backups, last_backup_at=self._backup_service.last_backup_at())


class GetBackupPathHandler(_Handler):
    async def handle(self, query: GetBackupPath) -> Path:
        return self._backup_service.path_for(query.name)


# --- Commands ---


class CreateBackupHandler(_Handler):
    async def handle(self, command: CreateBackup) -> BackupInfoDTO | None:
        current_revision = await self._repository.get_current_revision()
        if command.only_if_migrations_pending:
            if current_revision is None:
                return None
            head_revision = get_head_revision(get_settings().alembic_config_path)
            if current_revision == head_revision:
                return None
        backup = await self._backup_service.create(revision=current_revision)
        if command.actor_id is not None:
            await self._bus.execute(
                RecordAuditEvent(
                    actor_id=command.actor_id,
                    action=AuditAction.BACKUP_CREATED,
                    entity_type="backup",
                    entity_id=backup.name,
                    summary=f"Created backup {backup.name}",
                    details={"revision": backup.revision, "size_bytes": backup.size_bytes},
                )
            )
        return backup
