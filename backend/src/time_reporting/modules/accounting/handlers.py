"""Command and query handlers of the accounting module (registered in ``accounting.module``).

Handlers translate between bus messages and the service and never return ORM entities — the
service itself holds no ORM entities either, since this module owns no tables.
"""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.accounting.contracts import (
    AccountantPackageDTO,
    AccountantPackageStatusDTO,
    BuildAccountantPackage,
    GetAccountantPackageStatus,
)
from time_reporting.modules.accounting.service import AccountingService


class GetAccountantPackageStatusHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = AccountingService(bus)

    async def handle(self, query: GetAccountantPackageStatus) -> AccountantPackageStatusDTO:
        return await self._service.get_status(query)


class BuildAccountantPackageHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = AccountingService(bus)

    async def handle(self, query: BuildAccountantPackage) -> AccountantPackageDTO:
        return await self._service.build_package(query)
