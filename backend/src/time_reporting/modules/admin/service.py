"""Removal orchestration: archive by default, or permanently delete when nothing blocks it.

Reaches other modules only through their ``contracts.py`` messages. A permanent delete is one
outer command dispatched through the bus, so a failure partway through (e.g. deleting a user after
its memberships were already removed) rolls back everything.
"""

import logging
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.admin.contracts import (
    RemovalBlockedError,
    RemovalBlockerKind,
    RemovalCountDTO,
    RemovalEffectKind,
    RemovalImpactDTO,
    RemovalOutcome,
    RemovalTargetNotFoundError,
    SelfRemovalError,
)
from time_reporting.modules.customers.contracts import (
    CustomerInUseError,
    CustomerNotFoundError,
    DeleteCustomer,
    GetCustomerById,
    UpdateCustomer,
)
from time_reporting.modules.projects.contracts import (
    DeleteProject,
    GetProjectById,
    ListProjectBillingItems,
    ListProjectMembers,
    ListProjects,
    ProjectInUseError,
    ProjectNotFoundError,
    RemoveUserFromAllProjects,
    UpdateProject,
)
from time_reporting.modules.users.contracts import (
    DeleteUser,
    GetUserById,
    SelfModificationError,
    UpdateUser,
    UserInUseError,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)


class AdminRemovalService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    # --- Removal impact ---

    async def get_user_removal_impact(
        self, user_id: UUID, *, acting_user_id: UUID
    ) -> RemovalImpactDTO | None:
        user = await self._bus.query(GetUserById(user_id=user_id))
        if user is None:
            return None
        memberships = await self._bus.query(
            ListProjects(limit=1, offset=0, member_id=user_id, include_inactive=True)
        )
        blockers = []
        if user_id == acting_user_id:
            blockers.append(RemovalCountDTO(kind=RemovalBlockerKind.SELF, count=1))
        effects = []
        if memberships.total:
            effects.append(
                RemovalCountDTO(kind=RemovalEffectKind.PROJECT_MEMBERSHIPS, count=memberships.total)
            )
        return RemovalImpactDTO(
            is_active=user.is_active,
            can_delete_permanently=not blockers,
            blockers=tuple(blockers),
            effects=tuple(effects),
        )

    async def get_customer_removal_impact(self, customer_id: UUID) -> RemovalImpactDTO | None:
        customer = await self._bus.query(GetCustomerById(customer_id=customer_id))
        if customer is None:
            return None
        projects = await self._bus.query(
            ListProjects(limit=1, offset=0, customer_id=customer_id, include_inactive=True)
        )
        blockers = []
        if projects.total:
            blockers.append(RemovalCountDTO(kind=RemovalBlockerKind.PROJECTS, count=projects.total))
        return RemovalImpactDTO(
            is_active=customer.is_active,
            can_delete_permanently=not blockers,
            blockers=tuple(blockers),
            effects=(),
        )

    async def get_project_removal_impact(self, project_id: UUID) -> RemovalImpactDTO | None:
        project = await self._bus.query(GetProjectById(project_id=project_id))
        if project is None:
            return None
        members = await self._bus.query(ListProjectMembers(project_id=project_id))
        billing_items = await self._bus.query(
            ListProjectBillingItems(project_id=project_id, include_inactive=True)
        )
        effects = []
        if members:
            effects.append(
                RemovalCountDTO(kind=RemovalEffectKind.PROJECT_MEMBERS, count=len(members))
            )
        if billing_items:
            effects.append(
                RemovalCountDTO(
                    kind=RemovalEffectKind.PROJECT_BILLING_ITEMS, count=len(billing_items)
                )
            )
        return RemovalImpactDTO(
            is_active=project.is_active,
            can_delete_permanently=True,
            blockers=(),
            effects=tuple(effects),
        )

    # --- Removal (archive or delete) ---

    async def remove_user(
        self, user_id: UUID, *, acting_user_id: UUID, permanent: bool
    ) -> RemovalOutcome:
        if not permanent:
            try:
                await self._bus.execute(
                    UpdateUser(user_id=user_id, acting_user_id=acting_user_id, is_active=False)
                )
            except UserNotFoundError as exc:
                raise RemovalTargetNotFoundError(user_id) from exc
            except SelfModificationError as exc:
                raise SelfRemovalError() from exc
            return RemovalOutcome.ARCHIVED

        if user_id == acting_user_id:
            raise SelfRemovalError()

        impact = await self.get_user_removal_impact(user_id, acting_user_id=acting_user_id)
        if impact is None:
            raise RemovalTargetNotFoundError(user_id)
        if impact.blockers:
            raise RemovalBlockedError(impact.blockers)

        try:
            await self._bus.execute(RemoveUserFromAllProjects(user_id=user_id))
            await self._bus.execute(DeleteUser(user_id=user_id, acting_user_id=acting_user_id))
        except UserNotFoundError as exc:
            raise RemovalTargetNotFoundError(user_id) from exc
        except SelfModificationError as exc:
            raise SelfRemovalError() from exc
        except UserInUseError as exc:
            # A race with a concurrent insert after the impact check above; the exact count is
            # unknown at this point.
            raise RemovalBlockedError(
                (RemovalCountDTO(kind=RemovalBlockerKind.PROJECTS, count=0),)
            ) from exc
        logger.info("Permanently deleted user %s (by %s)", user_id, acting_user_id)
        return RemovalOutcome.DELETED

    async def remove_customer(self, customer_id: UUID, *, permanent: bool) -> RemovalOutcome:
        if not permanent:
            try:
                await self._bus.execute(UpdateCustomer(customer_id=customer_id, is_active=False))
            except CustomerNotFoundError as exc:
                raise RemovalTargetNotFoundError(customer_id) from exc
            return RemovalOutcome.ARCHIVED

        impact = await self.get_customer_removal_impact(customer_id)
        if impact is None:
            raise RemovalTargetNotFoundError(customer_id)
        if impact.blockers:
            raise RemovalBlockedError(impact.blockers)

        try:
            await self._bus.execute(DeleteCustomer(customer_id=customer_id))
        except CustomerNotFoundError as exc:
            raise RemovalTargetNotFoundError(customer_id) from exc
        except CustomerInUseError as exc:
            raise RemovalBlockedError(
                (RemovalCountDTO(kind=RemovalBlockerKind.PROJECTS, count=0),)
            ) from exc
        logger.info("Permanently deleted customer %s", customer_id)
        return RemovalOutcome.DELETED

    async def remove_project(self, project_id: UUID, *, permanent: bool) -> RemovalOutcome:
        if not permanent:
            try:
                await self._bus.execute(UpdateProject(project_id=project_id, is_active=False))
            except ProjectNotFoundError as exc:
                raise RemovalTargetNotFoundError(project_id) from exc
            return RemovalOutcome.ARCHIVED

        impact = await self.get_project_removal_impact(project_id)
        if impact is None:
            raise RemovalTargetNotFoundError(project_id)
        # Projects currently have no blockers; a future ProjectInUseError (e.g. time entries) is
        # still handled below in case that changes before the impact query catches up.

        try:
            await self._bus.execute(DeleteProject(project_id=project_id))
        except ProjectNotFoundError as exc:
            raise RemovalTargetNotFoundError(project_id) from exc
        except ProjectInUseError as exc:
            raise RemovalBlockedError(()) from exc
        logger.info("Permanently deleted project %s", project_id)
        return RemovalOutcome.DELETED
