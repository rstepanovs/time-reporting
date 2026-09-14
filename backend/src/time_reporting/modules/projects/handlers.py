"""Command and query handlers of the projects module (registered in ``projects.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from datetime import datetime

from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import CustomerDTO, GetCustomersByIds
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    CreateProject,
    DeleteProject,
    GetProjectById,
    ListProjectMembers,
    ListProjects,
    ProjectCustomerDTO,
    ProjectDTO,
    ProjectMemberDTO,
    ProjectNotFoundError,
    ProjectPageDTO,
    RemoveProjectMember,
    RemoveUserFromAllProjects,
    UpdateProject,
)
from time_reporting.modules.projects.models import Project
from time_reporting.modules.projects.repository import ProjectMemberRepository, ProjectRepository
from time_reporting.modules.projects.service import ProjectService
from time_reporting.modules.users.contracts import GetUsersByIds, UserDTO


def _customer_dto(customer: CustomerDTO) -> ProjectCustomerDTO:
    return ProjectCustomerDTO(id=customer.id, name=customer.name, is_active=customer.is_active)


def _member_dto(user: UserDTO, *, added_at: datetime) -> ProjectMemberDTO:
    return ProjectMemberDTO(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        added_at=added_at,
    )


def _to_dto(project: Project, customer: ProjectCustomerDTO) -> ProjectDTO:
    return ProjectDTO(
        id=project.id,
        customer=customer,
        name=project.name,
        description=project.description,
        is_active=project.is_active,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


class _BaseHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._projects = ProjectRepository(bus.session)

    async def _project_dto(self, project: Project) -> ProjectDTO:
        customers = await self._bus.query(
            GetCustomersByIds(customer_ids=frozenset({project.customer_id}))
        )
        return _to_dto(project, _customer_dto(customers[0]))


# --- Queries ---


class GetProjectByIdHandler(_BaseHandler):
    async def handle(self, query: GetProjectById) -> ProjectDTO | None:
        project = await self._projects.get_by_id(query.project_id)
        if project is None:
            return None
        return await self._project_dto(project)


class ListProjectsHandler(_BaseHandler):
    async def handle(self, query: ListProjects) -> ProjectPageDTO:
        projects = await self._projects.get_page(
            limit=query.limit,
            offset=query.offset,
            include_inactive=query.include_inactive,
            customer_id=query.customer_id,
            member_id=query.member_id,
            search=query.search,
        )
        total = await self._projects.count(
            include_inactive=query.include_inactive,
            customer_id=query.customer_id,
            member_id=query.member_id,
            search=query.search,
        )
        customer_ids = frozenset(project.customer_id for project in projects)
        customers_by_id = {
            customer.id: customer
            for customer in await self._bus.query(GetCustomersByIds(customer_ids=customer_ids))
        }
        items = tuple(
            _to_dto(project, _customer_dto(customers_by_id[project.customer_id]))
            for project in projects
        )
        return ProjectPageDTO(items=items, total=total, limit=query.limit, offset=query.offset)


class ListProjectMembersHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._projects = ProjectRepository(bus.session)
        self._members = ProjectMemberRepository(bus.session)

    async def handle(self, query: ListProjectMembers) -> tuple[ProjectMemberDTO, ...]:
        if await self._projects.get_by_id(query.project_id) is None:
            raise ProjectNotFoundError(query.project_id)

        links = await self._members.list_for_project(query.project_id)
        user_ids = frozenset(link.user_id for link in links)
        users_by_id = {
            user.id: user for user in await self._bus.query(GetUsersByIds(user_ids=user_ids))
        }
        members = []
        for link in links:
            user = users_by_id.get(link.user_id)
            if user is None:
                # Membership references users by table name (not a module import); a missing user
                # here means a users-module invariant was broken (e.g. a row deleted out-of-band).
                raise RuntimeError(f"Project member {link.user_id} has no matching user")
            members.append(_member_dto(user, added_at=link.created_at))
        members.sort(key=lambda member: (member.name, member.user_id))
        return tuple(members)


# --- Commands ---


class CreateProjectHandler(_BaseHandler):
    def __init__(self, bus: Bus) -> None:
        super().__init__(bus)
        self._service = ProjectService(bus)

    async def handle(self, command: CreateProject) -> ProjectDTO:
        project = await self._service.create_project(
            customer_id=command.customer_id, name=command.name, description=command.description
        )
        return await self._project_dto(project)


class UpdateProjectHandler(_BaseHandler):
    def __init__(self, bus: Bus) -> None:
        super().__init__(bus)
        self._service = ProjectService(bus)

    async def handle(self, command: UpdateProject) -> ProjectDTO:
        project = await self._service.update_project(command)
        return await self._project_dto(project)


class AddProjectMemberHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._service = ProjectService(bus)

    async def handle(self, command: AddProjectMember) -> ProjectMemberDTO:
        member = await self._service.add_member(
            project_id=command.project_id, user_id=command.user_id
        )
        users = await self._bus.query(GetUsersByIds(user_ids=frozenset({member.user_id})))
        return _member_dto(users[0], added_at=member.created_at)


class RemoveProjectMemberHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ProjectService(bus)

    async def handle(self, command: RemoveProjectMember) -> None:
        await self._service.remove_member(project_id=command.project_id, user_id=command.user_id)


class DeleteProjectHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ProjectService(bus)

    async def handle(self, command: DeleteProject) -> None:
        await self._service.delete_project(command.project_id)


class RemoveUserFromAllProjectsHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ProjectService(bus)

    async def handle(self, command: RemoveUserFromAllProjects) -> int:
        return await self._service.remove_user_from_all_projects(command.user_id)
