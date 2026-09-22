"""Project domain logic on ORM entities.

Changes are flushed through the repository; the bus commits. The service holds the ``Bus`` (not
just a session) because creating and re-activating a project need to check the owning customer via
``customers.contracts``, and adding a member needs to check the user via ``users.contracts``.
"""

from decimal import Decimal
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import GetCustomerById
from time_reporting.modules.projects.contracts import (
    DEFAULT_BILLING_ITEMS,
    BillingItemNameAlreadyExistsError,
    BillingItemNotFoundError,
    BillingItemPricingError,
    BillingUnit,
    MemberUserInactiveError,
    MemberUserNotFoundError,
    ProjectArchivedError,
    ProjectCustomerArchivedError,
    ProjectCustomerNotFoundError,
    ProjectManagerNotEligibleError,
    ProjectManagerNotFoundError,
    ProjectMemberNotFoundError,
    ProjectNameAlreadyExistsError,
    ProjectNotFoundError,
    UpdateProject,
    UpdateProjectBillingItem,
)
from time_reporting.modules.projects.models import Project, ProjectBillingItem, ProjectMember
from time_reporting.modules.projects.repository import (
    ProjectBillingItemRepository,
    ProjectMemberRepository,
    ProjectRepository,
)
from time_reporting.modules.users.contracts import GetUserById, UserRole


class ProjectService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._projects = ProjectRepository(bus.session)
        self._members = ProjectMemberRepository(bus.session)
        self._billing_items = ProjectBillingItemRepository(bus.session)

    async def get_project(self, project_id: UUID) -> Project:
        project = await self._projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    async def create_project(
        self,
        *,
        customer_id: UUID,
        name: str,
        description: str | None,
        normal_working_hours: Decimal,
        is_internal: bool,
        manager_id: UUID | None,
    ) -> Project:
        await self._ensure_customer_active(customer_id)
        await self._ensure_name_available(customer_id, name)
        if manager_id is not None:
            await self._ensure_manager_eligible(manager_id)
        project = Project(
            customer_id=customer_id,
            name=name,
            description=description,
            normal_working_hours=normal_working_hours,
            is_internal=is_internal,
            manager_id=manager_id,
        )
        await self._projects.save(project)
        await self._billing_items.add_all(
            ProjectBillingItem(
                project_id=project.id,
                preset=default.preset,
                name=default.name,
                unit=default.unit,
                position=position,
            )
            for position, default in enumerate(DEFAULT_BILLING_ITEMS, start=1)
        )
        return project

    async def update_project(self, data: UpdateProject) -> Project:
        project = await self.get_project(data.project_id)

        if data.name is not None and data.name != project.name:
            await self._ensure_name_available(project.customer_id, data.name)
            project.name = data.name
        if "description" in data.clear_fields:
            project.description = None
        elif data.description is not None:
            project.description = data.description
        if data.is_active is not None:
            if data.is_active and not project.is_active:
                # Re-activating a project requires its customer to still be active.
                await self._ensure_customer_active(project.customer_id)
            project.is_active = data.is_active
        if data.normal_working_hours is not None:
            project.normal_working_hours = data.normal_working_hours
        if data.is_internal is not None:
            project.is_internal = data.is_internal
        if "manager_id" in data.clear_fields:
            project.manager_id = None
        elif data.manager_id is not None:
            await self._ensure_manager_eligible(data.manager_id)
            project.manager_id = data.manager_id
        await self._projects.save(project)
        return project

    async def add_member(self, *, project_id: UUID, user_id: UUID) -> ProjectMember:
        await self._ensure_project_active(project_id)

        user = await self._bus.query(GetUserById(user_id=user_id))
        if user is None:
            raise MemberUserNotFoundError(user_id)
        if not user.is_active:
            raise MemberUserInactiveError(user_id)

        member = ProjectMember(project_id=project_id, user_id=user_id)
        await self._members.save(member)
        return member

    async def remove_member(self, *, project_id: UUID, user_id: UUID) -> None:
        await self.get_project(project_id)
        member = await self._members.get(project_id, user_id)
        if member is None:
            raise ProjectMemberNotFoundError(project_id, user_id)
        await self._members.delete(member)

    async def delete_project(self, project_id: UUID) -> None:
        await self._projects.delete(await self.get_project(project_id))

    async def remove_user_from_all_projects(self, user_id: UUID) -> int:
        await self._projects.clear_manager_for_user(user_id)
        return await self._members.delete_all_for_user(user_id)

    async def add_billing_item(
        self,
        *,
        project_id: UUID,
        name: str,
        unit: BillingUnit,
        description: str | None,
        unit_rate: Decimal | None,
        markup_percent: Decimal | None,
    ) -> ProjectBillingItem:
        await self._ensure_project_active(project_id)
        if unit_rate is not None:
            self._ensure_pricing_allowed(unit, "unit_rate")
        if markup_percent is not None:
            self._ensure_pricing_allowed(unit, "markup_percent")
        await self._ensure_billing_item_name_available(project_id, name)

        position = await self._billing_items.next_position(project_id)
        item = ProjectBillingItem(
            project_id=project_id,
            preset=None,
            name=name,
            description=description,
            unit=unit,
            unit_rate=unit_rate,
            markup_percent=markup_percent,
            position=position,
        )
        await self._billing_items.save(item)
        return item

    async def update_billing_item(self, data: UpdateProjectBillingItem) -> ProjectBillingItem:
        item = await self._get_billing_item(data.project_id, data.item_id)

        if data.name is not None and data.name != item.name:
            await self._ensure_billing_item_name_available(data.project_id, data.name)
            item.name = data.name
        if "description" in data.clear_fields:
            item.description = None
        elif data.description is not None:
            item.description = data.description
        if "unit_rate" in data.clear_fields:
            item.unit_rate = None
        elif data.unit_rate is not None:
            self._ensure_pricing_allowed(item.unit, "unit_rate")
            item.unit_rate = data.unit_rate
        if "markup_percent" in data.clear_fields:
            item.markup_percent = None
        elif data.markup_percent is not None:
            self._ensure_pricing_allowed(item.unit, "markup_percent")
            item.markup_percent = data.markup_percent
        if data.is_active is not None:
            if data.is_active and not item.is_active:
                # Re-activating an item requires its project to still be active.
                await self._ensure_project_active(data.project_id)
            item.is_active = data.is_active
        await self._billing_items.save(item)
        return item

    async def delete_billing_item(self, *, project_id: UUID, item_id: UUID) -> None:
        item = await self._get_billing_item(project_id, item_id)
        await self._billing_items.delete(item)

    async def _ensure_customer_active(self, customer_id: UUID) -> None:
        customer = await self._bus.query(GetCustomerById(customer_id=customer_id))
        if customer is None:
            raise ProjectCustomerNotFoundError(customer_id)
        if not customer.is_active:
            raise ProjectCustomerArchivedError(customer_id)

    async def _ensure_project_active(self, project_id: UUID) -> None:
        project = await self.get_project(project_id)
        if not project.is_active:
            raise ProjectArchivedError(project_id)

    async def _ensure_manager_eligible(self, user_id: UUID) -> None:
        user = await self._bus.query(GetUserById(user_id=user_id))
        if user is None:
            raise ProjectManagerNotFoundError(user_id)
        if not user.is_active or UserRole.MANAGER not in user.roles:
            raise ProjectManagerNotEligibleError(user_id)

    async def _ensure_name_available(self, customer_id: UUID, name: str) -> None:
        if await self._projects.get_by_customer_and_name(customer_id, name) is not None:
            raise ProjectNameAlreadyExistsError(customer_id, name)

    async def _ensure_billing_item_name_available(self, project_id: UUID, name: str) -> None:
        if await self._billing_items.get_by_project_and_name(project_id, name) is not None:
            raise BillingItemNameAlreadyExistsError(project_id, name)

    async def _get_billing_item(self, project_id: UUID, item_id: UUID) -> ProjectBillingItem:
        await self.get_project(project_id)  # raises ProjectNotFoundError if project_id is bogus
        item = await self._billing_items.get(project_id, item_id)
        if item is None:
            raise BillingItemNotFoundError(project_id, item_id)
        return item

    @staticmethod
    def _ensure_pricing_allowed(unit: BillingUnit, field: str) -> None:
        if field == "unit_rate" and unit is BillingUnit.AMOUNT:
            raise BillingItemPricingError(unit, field)
        if field == "markup_percent" and unit is not BillingUnit.AMOUNT:
            raise BillingItemPricingError(unit, field)
