"""Public contract of the projects module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``projects.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args
from uuid import UUID

from time_reporting.core.cqrs import Command, Query
from time_reporting.modules.users.contracts import UserRole

type ClearableProjectField = Literal["description"]

# Optional text fields that ``UpdateProject.clear_fields`` can reset to ``None``.
CLEARABLE_PROJECT_FIELDS: tuple[ClearableProjectField, ...] = get_args(
    ClearableProjectField.__value__
)


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectCustomerDTO:
    """The subset of a project's customer needed to display it alongside the project."""

    id: UUID
    name: str
    is_active: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectDTO:
    id: UUID
    customer: ProjectCustomerDTO
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectPageDTO:
    items: tuple[ProjectDTO, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectMemberDTO:
    user_id: UUID
    name: str
    email: str
    role: UserRole
    is_active: bool
    added_at: datetime


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectById(Query[ProjectDTO | None]):
    project_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProjects(Query[ProjectPageDTO]):
    """Projects ordered by name; archived (inactive) ones only if ``include_inactive``."""

    limit: int
    offset: int
    include_inactive: bool = False
    customer_id: UUID | None = None
    member_id: UUID | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProjectMembers(Query[tuple[ProjectMemberDTO, ...]]):
    """Members of a project, ordered by name.

    Raises ``ProjectNotFoundError`` if the project doesn't exist.
    """

    project_id: UUID


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateProject(Command[ProjectDTO]):
    customer_id: UUID
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateProject(Command[ProjectDTO]):
    """Partial update: fields left as ``None`` are not changed.

    ``customer_id`` is immutable and not part of this command. The optional ``description`` is
    cleared by naming it in ``clear_fields``. Projects are never deleted; archive them with
    ``is_active=False``. Re-activating a project under an archived customer is rejected.
    """

    project_id: UUID
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    clear_fields: frozenset[ClearableProjectField] = frozenset()


@dataclass(frozen=True, slots=True, kw_only=True)
class AddProjectMember(Command[ProjectMemberDTO]):
    project_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveProjectMember(Command[None]):
    project_id: UUID
    user_id: UUID


# --- Exceptions ---


class ProjectError(Exception):
    """Base class for projects module domain errors."""


class ProjectNotFoundError(ProjectError):
    def __init__(self, project_id: UUID) -> None:
        super().__init__(f"Project {project_id} not found")
        self.project_id = project_id


class ProjectNameAlreadyExistsError(ProjectError):
    def __init__(self, customer_id: UUID, name: str) -> None:
        super().__init__(f"A project named {name!r} already exists for customer {customer_id}")
        self.customer_id = customer_id
        self.name = name


class ProjectCustomerNotFoundError(ProjectError):
    def __init__(self, customer_id: UUID) -> None:
        super().__init__(f"Customer {customer_id} not found")
        self.customer_id = customer_id


class ProjectCustomerArchivedError(ProjectError):
    def __init__(self, customer_id: UUID) -> None:
        super().__init__(f"Customer {customer_id} is archived")
        self.customer_id = customer_id


class ProjectArchivedError(ProjectError):
    def __init__(self, project_id: UUID) -> None:
        super().__init__(f"Project {project_id} is archived")
        self.project_id = project_id


class MemberUserNotFoundError(ProjectError):
    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User {user_id} not found")
        self.user_id = user_id


class MemberUserInactiveError(ProjectError):
    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User {user_id} is inactive")
        self.user_id = user_id


class ProjectMemberAlreadyExistsError(ProjectError):
    def __init__(self, project_id: UUID, user_id: UUID) -> None:
        super().__init__(f"User {user_id} is already a member of project {project_id}")
        self.project_id = project_id
        self.user_id = user_id


class ProjectMemberNotFoundError(ProjectError):
    def __init__(self, project_id: UUID, user_id: UUID) -> None:
        super().__init__(f"User {user_id} is not a member of project {project_id}")
        self.project_id = project_id
        self.user_id = user_id
