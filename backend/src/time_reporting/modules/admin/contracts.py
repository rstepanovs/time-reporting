"""Public contract of the admin module.

Other modules do not depend on this one (it sits above ``users``/``customers``/``projects``), but
its own handlers reach those modules only through their ``contracts.py``, per the module boundary
rule. ORM entities never leave any module.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from time_reporting.core.cqrs import Command, Query


class RemovalOutcome(StrEnum):
    ARCHIVED = "archived"
    DELETED = "deleted"


class RemovalBlockerKind(StrEnum):
    """What prevents a permanent delete."""

    SELF = "self"
    PROJECTS = "projects"
    TIME_ENTRIES = "time_entries"
    INVOICES = "invoices"


class RemovalEffectKind(StrEnum):
    """What a permanent delete also removes, in addition to the record itself."""

    PROJECT_MEMBERSHIPS = "project_memberships"
    MANAGED_PROJECTS = "managed_projects"
    PROJECT_MEMBERS = "project_members"
    PROJECT_BILLING_ITEMS = "project_billing_items"


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class RemovalCountDTO:
    kind: RemovalBlockerKind | RemovalEffectKind
    # The number of affected rows; 0 for a kind detected only as a race at delete time (the
    # foreign-key violation carries no count).
    count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RemovalImpactDTO:
    is_active: bool
    can_delete_permanently: bool
    blockers: tuple[RemovalCountDTO, ...]
    effects: tuple[RemovalCountDTO, ...]


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetUserRemovalImpact(Query[RemovalImpactDTO | None]):
    user_id: UUID
    acting_user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCustomerRemovalImpact(Query[RemovalImpactDTO | None]):
    customer_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectRemovalImpact(Query[RemovalImpactDTO | None]):
    project_id: UUID


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveUser(Command[RemovalOutcome]):
    """Archive (default) or, with ``permanent``, permanently delete a user."""

    user_id: UUID
    acting_user_id: UUID
    permanent: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveCustomer(Command[RemovalOutcome]):
    customer_id: UUID
    acting_user_id: UUID
    permanent: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveProject(Command[RemovalOutcome]):
    project_id: UUID
    acting_user_id: UUID
    permanent: bool = False


# --- Exceptions ---


class AdminError(Exception):
    """Base class for admin module domain errors."""


class RemovalTargetNotFoundError(AdminError):
    def __init__(self, target_id: UUID) -> None:
        super().__init__(f"{target_id} not found")
        self.target_id = target_id


class SelfRemovalError(AdminError):
    def __init__(self) -> None:
        super().__init__("You cannot archive or delete your own account")


class RemovalBlockedError(AdminError):
    """A permanent delete was refused because other data still references the record."""

    def __init__(self, blockers: tuple[RemovalCountDTO, ...]) -> None:
        super().__init__("This record is referenced by other data and cannot be deleted")
        self.blockers = blockers
