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
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.customers.contracts import (
    CustomerInUseError,
    CustomerNotFoundError,
    DeleteCustomer,
    GetCustomerById,
    UpdateCustomer,
)
from time_reporting.modules.invoices.contracts import CountInvoices
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
from time_reporting.modules.timesheets.contracts import CountTimeEntries
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
        managed_projects = await self._bus.query(
            ListProjects(limit=1, offset=0, manager_id=user_id, include_inactive=True)
        )
        time_entry_count = await self._bus.query(CountTimeEntries(user_id=user_id))
        blockers = []
        if user_id == acting_user_id:
            blockers.append(RemovalCountDTO(kind=RemovalBlockerKind.SELF, count=1))
        if time_entry_count:
            blockers.append(
                RemovalCountDTO(kind=RemovalBlockerKind.TIME_ENTRIES, count=time_entry_count)
            )
        effects = []
        if memberships.total:
            effects.append(
                RemovalCountDTO(kind=RemovalEffectKind.PROJECT_MEMBERSHIPS, count=memberships.total)
            )
        if managed_projects.total:
            effects.append(
                RemovalCountDTO(
                    kind=RemovalEffectKind.MANAGED_PROJECTS, count=managed_projects.total
                )
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
        invoice_count = await self._bus.query(CountInvoices(customer_id=customer_id))
        blockers = []
        if projects.total:
            blockers.append(RemovalCountDTO(kind=RemovalBlockerKind.PROJECTS, count=projects.total))
        if invoice_count:
            blockers.append(RemovalCountDTO(kind=RemovalBlockerKind.INVOICES, count=invoice_count))
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
        time_entry_count = await self._bus.query(CountTimeEntries(project_id=project_id))
        blockers = []
        if time_entry_count:
            blockers.append(
                RemovalCountDTO(kind=RemovalBlockerKind.TIME_ENTRIES, count=time_entry_count)
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
            can_delete_permanently=not blockers,
            blockers=tuple(blockers),
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

        # Fetched before the delete so the audit event below still has a name to show.
        user = await self._bus.query(GetUserById(user_id=user_id))
        assert user is not None  # confirmed to exist by the impact check above

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
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=acting_user_id,
                action=AuditAction.USER_DELETED,
                entity_type="user",
                entity_id=str(user_id),
                summary=f"Permanently deleted user {user.name} ({user.email})",
            )
        )
        logger.info("Permanently deleted user %s (by %s)", user_id, acting_user_id)
        return RemovalOutcome.DELETED

    async def remove_customer(
        self, customer_id: UUID, *, acting_user_id: UUID, permanent: bool
    ) -> RemovalOutcome:
        customer = await self._bus.query(GetCustomerById(customer_id=customer_id))
        if customer is None:
            raise RemovalTargetNotFoundError(customer_id)

        if not permanent:
            try:
                await self._bus.execute(UpdateCustomer(customer_id=customer_id, is_active=False))
            except CustomerNotFoundError as exc:
                raise RemovalTargetNotFoundError(customer_id) from exc
            await self._bus.execute(
                RecordAuditEvent(
                    actor_id=acting_user_id,
                    action=AuditAction.CUSTOMER_ARCHIVED,
                    entity_type="customer",
                    entity_id=str(customer_id),
                    summary=f"Archived customer {customer.name}",
                )
            )
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
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=acting_user_id,
                action=AuditAction.CUSTOMER_DELETED,
                entity_type="customer",
                entity_id=str(customer_id),
                summary=f"Permanently deleted customer {customer.name}",
            )
        )
        logger.info("Permanently deleted customer %s", customer_id)
        return RemovalOutcome.DELETED

    async def remove_project(
        self, project_id: UUID, *, acting_user_id: UUID, permanent: bool
    ) -> RemovalOutcome:
        project = await self._bus.query(GetProjectById(project_id=project_id))
        if project is None:
            raise RemovalTargetNotFoundError(project_id)
        project_label = f"{project.customer.name} · {project.name}"

        if not permanent:
            try:
                await self._bus.execute(UpdateProject(project_id=project_id, is_active=False))
            except ProjectNotFoundError as exc:
                raise RemovalTargetNotFoundError(project_id) from exc
            await self._bus.execute(
                RecordAuditEvent(
                    actor_id=acting_user_id,
                    action=AuditAction.PROJECT_ARCHIVED,
                    entity_type="project",
                    entity_id=str(project_id),
                    summary=f"Archived project {project_label}",
                )
            )
            return RemovalOutcome.ARCHIVED

        impact = await self.get_project_removal_impact(project_id)
        if impact is None:
            raise RemovalTargetNotFoundError(project_id)
        if impact.blockers:
            raise RemovalBlockedError(impact.blockers)

        try:
            await self._bus.execute(DeleteProject(project_id=project_id))
        except ProjectNotFoundError as exc:
            raise RemovalTargetNotFoundError(project_id) from exc
        except ProjectInUseError as exc:
            # A race with a concurrent time entry added after the impact check above; the exact
            # count is unknown at this point.
            raise RemovalBlockedError(
                (RemovalCountDTO(kind=RemovalBlockerKind.TIME_ENTRIES, count=0),)
            ) from exc
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=acting_user_id,
                action=AuditAction.PROJECT_DELETED,
                entity_type="project",
                entity_id=str(project_id),
                summary=f"Permanently deleted project {project_label}",
            )
        )
        logger.info("Permanently deleted project %s", project_id)
        return RemovalOutcome.DELETED
