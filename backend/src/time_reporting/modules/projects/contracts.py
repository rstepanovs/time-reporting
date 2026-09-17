"""Public contract of the projects module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``projects.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, get_args
from uuid import UUID

from time_reporting.core.cqrs import Command, Query
from time_reporting.modules.users.contracts import UserRole

type ClearableProjectField = Literal["description", "manager_id"]

# Optional text fields that ``UpdateProject.clear_fields`` can reset to ``None``.
CLEARABLE_PROJECT_FIELDS: tuple[ClearableProjectField, ...] = get_args(
    ClearableProjectField.__value__
)

type ClearableBillingItemField = Literal["description", "unit_rate", "markup_percent"]

# Optional fields that ``UpdateProjectBillingItem.clear_fields`` can reset to ``None``.
CLEARABLE_BILLING_ITEM_FIELDS: tuple[ClearableBillingItemField, ...] = get_args(
    ClearableBillingItemField.__value__
)


class BillingUnit(StrEnum):
    """What a billing item's quantity is measured in. Immutable once the item exists."""

    HOUR = "hour"
    DAY = "day"
    # An expense entered as a money amount, billed at cost plus the item's optional markup.
    AMOUNT = "amount"


class BillingItemPreset(StrEnum):
    """Identifies a billing item created from ``DEFAULT_BILLING_ITEMS``; custom items have none."""

    NORMAL_HOURS = "normal_hours"
    OVERTIME_HOURS = "overtime_hours"
    TRAVEL_TIME = "travel_time"
    PER_DIEM = "per_diem"
    PURCHASING_EXPENSES = "purchasing_expenses"
    OTHER_EXPENSES = "other_expenses"


@dataclass(frozen=True, slots=True, kw_only=True)
class DefaultBillingItem:
    preset: BillingItemPreset
    name: str
    unit: BillingUnit


# Copied, in this order and without rates, into every newly created project.
DEFAULT_BILLING_ITEMS: tuple[DefaultBillingItem, ...] = (
    DefaultBillingItem(
        preset=BillingItemPreset.NORMAL_HOURS, name="Normal working hours", unit=BillingUnit.HOUR
    ),
    DefaultBillingItem(
        preset=BillingItemPreset.OVERTIME_HOURS,
        name="Overtime working hours",
        unit=BillingUnit.HOUR,
    ),
    DefaultBillingItem(
        preset=BillingItemPreset.TRAVEL_TIME, name="Travel time", unit=BillingUnit.HOUR
    ),
    DefaultBillingItem(preset=BillingItemPreset.PER_DIEM, name="Per diems", unit=BillingUnit.DAY),
    DefaultBillingItem(
        preset=BillingItemPreset.PURCHASING_EXPENSES,
        name="Purchasing expenses",
        unit=BillingUnit.AMOUNT,
    ),
    DefaultBillingItem(
        preset=BillingItemPreset.OTHER_EXPENSES, name="Other expenses", unit=BillingUnit.AMOUNT
    ),
)


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectCustomerDTO:
    """The subset of a project's customer needed to display it alongside the project."""

    id: UUID
    name: str
    is_active: bool
    # ISO 4217 code; billing item rates are in this currency.
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectManagerDTO:
    """The subset of a project's manager needed to display it alongside the project."""

    id: UUID
    name: str
    email: str
    is_active: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectDTO:
    id: UUID
    customer: ProjectCustomerDTO
    name: str
    description: str | None
    is_active: bool
    # Hours booked per working day when a timesheet week is prefilled for this project.
    normal_working_hours: Decimal
    manager: ProjectManagerDTO | None
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
    roles: frozenset[UserRole]
    is_active: bool
    added_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectBillingItemDTO:
    id: UUID
    project_id: UUID
    preset: BillingItemPreset | None
    name: str
    description: str | None
    unit: BillingUnit
    unit_rate: Decimal | None
    markup_percent: Decimal | None
    position: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectOptionDTO:
    """A project the caller is a member of, with its active billing items.

    Used to build a "which project/billing item" picker (e.g. adding a timesheet row) and to
    validate that a write against a given project/billing item is allowed for that user.
    """

    project: ProjectDTO
    billing_items: tuple[ProjectBillingItemDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ManagedProjectDTO:
    """A project with its members, for a manager's team overview."""

    project: ProjectDTO
    members: tuple[ProjectMemberDTO, ...]


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectById(Query[ProjectDTO | None]):
    project_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectsByIds(Query[tuple[ProjectDTO, ...]]):
    """Projects matching ``project_ids``, ordered by name then id. Unknown ids are silently
    omitted."""

    project_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectBillingItemsByIds(Query[tuple[ProjectBillingItemDTO, ...]]):
    """Billing items matching ``billing_item_ids``, ordered by project then position then name.
    Unknown ids are silently omitted."""

    billing_item_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True, kw_only=True)
class ListMemberProjectsWithBillingItems(Query[tuple[ProjectOptionDTO, ...]]):
    """Active projects ``user_id`` is a member of, each with its active billing items, ordered by
    project name. Used to build a timesheet row picker and to validate timesheet writes.

    ``units=None`` (the default) returns every unit; ``timesheets`` passes ``{HOUR, DAY}`` and
    ``expenses`` passes ``{AMOUNT}`` so each module only ever sees the items it can write to. A
    project whose every billing item is filtered out by ``units`` is dropped from the result.
    """

    user_id: UUID
    units: frozenset[BillingUnit] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListManagedProjectsWithMembers(Query[tuple[ManagedProjectDTO, ...]]):
    """Active projects with their members, ordered by customer name then project name.

    ``manager_id=None`` returns every active project (an admin's "all" view); otherwise only
    projects managed by that user. Used to build a manager's team overview.
    """

    manager_id: UUID | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProjects(Query[ProjectPageDTO]):
    """Projects ordered by name; archived (inactive) ones only if ``include_inactive``."""

    limit: int
    offset: int
    include_inactive: bool = False
    customer_id: UUID | None = None
    member_id: UUID | None = None
    manager_id: UUID | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProjectMembers(Query[tuple[ProjectMemberDTO, ...]]):
    """Members of a project, ordered by name.

    Raises ``ProjectNotFoundError`` if the project doesn't exist.
    """

    project_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProjectBillingItems(Query[tuple[ProjectBillingItemDTO, ...]]):
    """Billing items of a project, ordered by position then name; archived ones only if
    ``include_inactive``.

    Raises ``ProjectNotFoundError`` if the project doesn't exist.
    """

    project_id: UUID
    include_inactive: bool = False


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateProject(Command[ProjectDTO]):
    customer_id: UUID
    name: str
    description: str | None = None
    normal_working_hours: Decimal = Decimal("8.00")
    manager_id: UUID | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateProject(Command[ProjectDTO]):
    """Partial update: fields left as ``None`` are not changed.

    ``customer_id`` is immutable and not part of this command. The optional ``description`` and
    ``manager_id`` are cleared by naming them in ``clear_fields``. Archive a project with
    ``is_active=False``; permanently deleting an unreferenced one goes through the admin module's
    ``DeleteProject``. Re-activating a project under an archived customer is rejected.
    """

    project_id: UUID
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    normal_working_hours: Decimal | None = None
    manager_id: UUID | None = None
    clear_fields: frozenset[ClearableProjectField] = frozenset()


@dataclass(frozen=True, slots=True, kw_only=True)
class AddProjectMember(Command[ProjectMemberDTO]):
    project_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveProjectMember(Command[None]):
    project_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteProject(Command[None]):
    """Permanently delete a project and its memberships (cascade). May raise ``ProjectInUseError``
    if other data (e.g. future time entries) still references it."""

    project_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveUserFromAllProjects(Command[int]):
    """Delete every membership of ``user_id`` and clear it as any project's ``manager_id``,
    returning how many memberships were removed.

    Used before permanently deleting a user, whose id is referenced (``ON DELETE RESTRICT``) by
    ``project_members`` and by ``projects.manager_id``.
    """

    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class AddProjectBillingItem(Command[ProjectBillingItemDTO]):
    """Add a custom billing item (``preset=None``) at the end of the project's item list.

    The project must exist and be active. ``unit_rate`` is only accepted for ``hour``/``day``
    items, ``markup_percent`` only for ``amount`` items; either can be left ``None`` ("not set").
    """

    project_id: UUID
    name: str
    unit: BillingUnit
    description: str | None = None
    unit_rate: Decimal | None = None
    markup_percent: Decimal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateProjectBillingItem(Command[ProjectBillingItemDTO]):
    """Partial update: fields left as ``None`` are not changed.

    ``unit`` and ``preset`` are immutable and not part of this command (also for default items,
    which can otherwise be renamed and archived like any other item). ``description``,
    ``unit_rate`` and ``markup_percent`` are cleared by naming them in ``clear_fields``. Archive an
    item with ``is_active=False``; permanently deleting an unreferenced one goes through the admin
    module. Re-activating an item under an archived project is rejected.
    """

    project_id: UUID
    item_id: UUID
    name: str | None = None
    description: str | None = None
    unit_rate: Decimal | None = None
    markup_percent: Decimal | None = None
    is_active: bool | None = None
    clear_fields: frozenset[ClearableBillingItemField] = frozenset()


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteProjectBillingItem(Command[None]):
    """Permanently delete a billing item. May raise ``BillingItemInUseError`` if other data (e.g.
    future time entries) still references it."""

    project_id: UUID
    item_id: UUID


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


class ProjectManagerNotFoundError(ProjectError):
    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User {user_id} not found")
        self.user_id = user_id


class ProjectManagerNotEligibleError(ProjectError):
    """Raised when the given user is inactive or does not hold the ``manager`` access level."""

    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User {user_id} cannot be assigned as a project manager")
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


class ProjectInUseError(ProjectError):
    """Raised when deleting a project blocked by other data referencing it."""

    def __init__(self, project_id: UUID) -> None:
        super().__init__(f"Project {project_id} is referenced by other data and cannot be deleted")
        self.project_id = project_id


class BillingItemNotFoundError(ProjectError):
    def __init__(self, project_id: UUID, item_id: UUID) -> None:
        super().__init__(f"Billing item {item_id} not found for project {project_id}")
        self.project_id = project_id
        self.item_id = item_id


class BillingItemNameAlreadyExistsError(ProjectError):
    def __init__(self, project_id: UUID, name: str) -> None:
        super().__init__(f"A billing item named {name!r} already exists for project {project_id}")
        self.project_id = project_id
        self.name = name


class BillingItemPricingError(ProjectError):
    """Raised when a rate or markup is given for a unit that doesn't take it."""

    def __init__(self, unit: BillingUnit, field: str) -> None:
        super().__init__(f"`{field}` is not allowed for `{unit}` items")
        self.unit = unit
        self.field = field


class BillingItemInUseError(ProjectError):
    """Raised when deleting a billing item blocked by other data referencing it."""

    def __init__(self, item_id: UUID) -> None:
        super().__init__(
            f"Billing item {item_id} is referenced by other data and cannot be deleted"
        )
        self.item_id = item_id
