"""Registers the projects module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.projects.contracts import (
    AddProjectBillingItem,
    AddProjectMember,
    CreateProject,
    DeleteProject,
    DeleteProjectBillingItem,
    GetProjectBillingItemsByIds,
    GetProjectById,
    GetProjectsByIds,
    ListManagedProjectsWithMembers,
    ListMemberProjectsWithBillingItems,
    ListProjectBillingItems,
    ListProjectMembers,
    ListProjects,
    RemoveProjectMember,
    RemoveUserFromAllProjects,
    UpdateProject,
    UpdateProjectBillingItem,
)
from time_reporting.modules.projects.handlers import (
    AddProjectBillingItemHandler,
    AddProjectMemberHandler,
    CreateProjectHandler,
    DeleteProjectBillingItemHandler,
    DeleteProjectHandler,
    GetProjectBillingItemsByIdsHandler,
    GetProjectByIdHandler,
    GetProjectsByIdsHandler,
    ListManagedProjectsWithMembersHandler,
    ListMemberProjectsWithBillingItemsHandler,
    ListProjectBillingItemsHandler,
    ListProjectMembersHandler,
    ListProjectsHandler,
    RemoveProjectMemberHandler,
    RemoveUserFromAllProjectsHandler,
    UpdateProjectBillingItemHandler,
    UpdateProjectHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetProjectById, GetProjectByIdHandler)
    registry.query(GetProjectsByIds, GetProjectsByIdsHandler)
    registry.query(GetProjectBillingItemsByIds, GetProjectBillingItemsByIdsHandler)
    registry.query(ListMemberProjectsWithBillingItems, ListMemberProjectsWithBillingItemsHandler)
    registry.query(ListManagedProjectsWithMembers, ListManagedProjectsWithMembersHandler)
    registry.query(ListProjects, ListProjectsHandler)
    registry.query(ListProjectMembers, ListProjectMembersHandler)
    registry.query(ListProjectBillingItems, ListProjectBillingItemsHandler)

    registry.command(CreateProject, CreateProjectHandler)
    registry.command(UpdateProject, UpdateProjectHandler)
    registry.command(AddProjectMember, AddProjectMemberHandler)
    registry.command(RemoveProjectMember, RemoveProjectMemberHandler)
    registry.command(DeleteProject, DeleteProjectHandler)
    registry.command(RemoveUserFromAllProjects, RemoveUserFromAllProjectsHandler)
    registry.command(AddProjectBillingItem, AddProjectBillingItemHandler)
    registry.command(UpdateProjectBillingItem, UpdateProjectBillingItemHandler)
    registry.command(DeleteProjectBillingItem, DeleteProjectBillingItemHandler)
