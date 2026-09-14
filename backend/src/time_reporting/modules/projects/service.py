"""Project domain logic on ORM entities.

Changes are flushed through the repository; the bus commits. The service holds the ``Bus`` (not
just a session) because creating and re-activating a project need to check the owning customer via
``customers.contracts``, and adding a member needs to check the user via ``users.contracts``.
"""

from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import GetCustomerById
from time_reporting.modules.projects.contracts import (
    MemberUserInactiveError,
    MemberUserNotFoundError,
    ProjectArchivedError,
    ProjectCustomerArchivedError,
    ProjectCustomerNotFoundError,
    ProjectMemberNotFoundError,
    ProjectNameAlreadyExistsError,
    ProjectNotFoundError,
    UpdateProject,
)
from time_reporting.modules.projects.models import Project, ProjectMember
from time_reporting.modules.projects.repository import ProjectMemberRepository, ProjectRepository
from time_reporting.modules.users.contracts import GetUserById


class ProjectService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._projects = ProjectRepository(bus.session)
        self._members = ProjectMemberRepository(bus.session)

    async def get_project(self, project_id: UUID) -> Project:
        project = await self._projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    async def create_project(
        self, *, customer_id: UUID, name: str, description: str | None
    ) -> Project:
        await self._ensure_customer_active(customer_id)
        await self._ensure_name_available(customer_id, name)
        project = Project(customer_id=customer_id, name=name, description=description)
        await self._projects.save(project)
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
        await self._projects.save(project)
        return project

    async def add_member(self, *, project_id: UUID, user_id: UUID) -> ProjectMember:
        project = await self.get_project(project_id)
        if not project.is_active:
            raise ProjectArchivedError(project_id)

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

    async def _ensure_customer_active(self, customer_id: UUID) -> None:
        customer = await self._bus.query(GetCustomerById(customer_id=customer_id))
        if customer is None:
            raise ProjectCustomerNotFoundError(customer_id)
        if not customer.is_active:
            raise ProjectCustomerArchivedError(customer_id)

    async def _ensure_name_available(self, customer_id: UUID, name: str) -> None:
        if await self._projects.get_by_customer_and_name(customer_id, name) is not None:
            raise ProjectNameAlreadyExistsError(customer_id, name)
