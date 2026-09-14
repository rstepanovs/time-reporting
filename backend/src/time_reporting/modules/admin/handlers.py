"""Command and query handlers of the admin module (registered in ``admin.module``)."""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.admin.contracts import (
    GetCustomerRemovalImpact,
    GetProjectRemovalImpact,
    GetUserRemovalImpact,
    RemovalImpactDTO,
    RemovalOutcome,
    RemoveCustomer,
    RemoveProject,
    RemoveUser,
)
from time_reporting.modules.admin.service import AdminRemovalService


class _Handler:
    def __init__(self, bus: Bus) -> None:
        self._service = AdminRemovalService(bus)


# --- Queries ---


class GetUserRemovalImpactHandler(_Handler):
    async def handle(self, query: GetUserRemovalImpact) -> RemovalImpactDTO | None:
        return await self._service.get_user_removal_impact(
            query.user_id, acting_user_id=query.acting_user_id
        )


class GetCustomerRemovalImpactHandler(_Handler):
    async def handle(self, query: GetCustomerRemovalImpact) -> RemovalImpactDTO | None:
        return await self._service.get_customer_removal_impact(query.customer_id)


class GetProjectRemovalImpactHandler(_Handler):
    async def handle(self, query: GetProjectRemovalImpact) -> RemovalImpactDTO | None:
        return await self._service.get_project_removal_impact(query.project_id)


# --- Commands ---


class RemoveUserHandler(_Handler):
    async def handle(self, command: RemoveUser) -> RemovalOutcome:
        return await self._service.remove_user(
            command.user_id,
            acting_user_id=command.acting_user_id,
            permanent=command.permanent,
        )


class RemoveCustomerHandler(_Handler):
    async def handle(self, command: RemoveCustomer) -> RemovalOutcome:
        return await self._service.remove_customer(command.customer_id, permanent=command.permanent)


class RemoveProjectHandler(_Handler):
    async def handle(self, command: RemoveProject) -> RemovalOutcome:
        return await self._service.remove_project(command.project_id, permanent=command.permanent)
