"""Query handlers of the system module (registered in ``system.module``)."""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.system.contracts import (
    GetSystemConfig,
    GetSystemStatus,
    SystemConfigDTO,
    SystemStatusDTO,
)
from time_reporting.modules.system.repository import SystemRepository
from time_reporting.modules.system.service import SystemService


class _Handler:
    def __init__(self, bus: Bus) -> None:
        self._service = SystemService(SystemRepository(bus.session))


class GetSystemStatusHandler(_Handler):
    async def handle(self, query: GetSystemStatus) -> SystemStatusDTO:
        return await self._service.get_status(started_at=query.started_at)


class GetSystemConfigHandler(_Handler):
    async def handle(self, query: GetSystemConfig) -> SystemConfigDTO:
        return await self._service.get_config()
