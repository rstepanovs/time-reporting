"""Registers the system module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.system.contracts import (
    CreateBackup,
    GetBackupPath,
    GetSystemConfig,
    GetSystemStatus,
    ListBackups,
)
from time_reporting.modules.system.handlers import (
    CreateBackupHandler,
    GetBackupPathHandler,
    GetSystemConfigHandler,
    GetSystemStatusHandler,
    ListBackupsHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetSystemStatus, GetSystemStatusHandler)
    registry.query(GetSystemConfig, GetSystemConfigHandler)
    registry.query(ListBackups, ListBackupsHandler)
    registry.query(GetBackupPath, GetBackupPathHandler)
    registry.command(CreateBackup, CreateBackupHandler)
