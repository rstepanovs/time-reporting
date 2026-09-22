"""Registers the accounting module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.accounting.contracts import (
    BuildAccountantPackage,
    GetAccountantPackageStatus,
)
from time_reporting.modules.accounting.handlers import (
    BuildAccountantPackageHandler,
    GetAccountantPackageStatusHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetAccountantPackageStatus, GetAccountantPackageStatusHandler)
    registry.query(BuildAccountantPackage, BuildAccountantPackageHandler)
