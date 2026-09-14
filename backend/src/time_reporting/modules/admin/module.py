"""Registers the admin module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.admin.contracts import (
    GetCustomerRemovalImpact,
    GetProjectRemovalImpact,
    GetUserRemovalImpact,
    RemoveCustomer,
    RemoveProject,
    RemoveUser,
)
from time_reporting.modules.admin.handlers import (
    GetCustomerRemovalImpactHandler,
    GetProjectRemovalImpactHandler,
    GetUserRemovalImpactHandler,
    RemoveCustomerHandler,
    RemoveProjectHandler,
    RemoveUserHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetUserRemovalImpact, GetUserRemovalImpactHandler)
    registry.query(GetCustomerRemovalImpact, GetCustomerRemovalImpactHandler)
    registry.query(GetProjectRemovalImpact, GetProjectRemovalImpactHandler)

    registry.command(RemoveUser, RemoveUserHandler)
    registry.command(RemoveCustomer, RemoveCustomerHandler)
    registry.command(RemoveProject, RemoveProjectHandler)
