"""Registers the projects module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    CreateProject,
    DeleteProject,
    GetProjectById,
    ListProjectMembers,
    ListProjects,
    RemoveProjectMember,
    RemoveUserFromAllProjects,
    UpdateProject,
)
from time_reporting.modules.projects.handlers import (
    AddProjectMemberHandler,
    CreateProjectHandler,
    DeleteProjectHandler,
    GetProjectByIdHandler,
    ListProjectMembersHandler,
    ListProjectsHandler,
    RemoveProjectMemberHandler,
    RemoveUserFromAllProjectsHandler,
    UpdateProjectHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetProjectById, GetProjectByIdHandler)
    registry.query(ListProjects, ListProjectsHandler)
    registry.query(ListProjectMembers, ListProjectMembersHandler)

    registry.command(CreateProject, CreateProjectHandler)
    registry.command(UpdateProject, UpdateProjectHandler)
    registry.command(AddProjectMember, AddProjectMemberHandler)
    registry.command(RemoveProjectMember, RemoveProjectMemberHandler)
    registry.command(DeleteProject, DeleteProjectHandler)
    registry.command(RemoveUserFromAllProjects, RemoveUserFromAllProjectsHandler)
