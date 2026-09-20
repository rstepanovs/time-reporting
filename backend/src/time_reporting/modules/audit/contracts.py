"""Public contract of the audit module.

Owns no tables of its own conceptually beyond the immutable event log: other modules record an
event by executing ``RecordAuditEvent`` as a *nested* command from within their own command
handler, so the event commits or rolls back together with the change it describes — never on its
own. This module in turn depends on ``users.contracts`` (``GetUserById``) to resolve an actor's
display name at record time.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from time_reporting.core.cqrs import Command, Query


class AuditAction(StrEnum):
    """What happened. New members are expected to be added regularly as more of the app grows
    audit coverage, so this is a plain Python enum, not a Postgres one — no migration is needed to
    add a value (see ``AuditEvent.action`` in ``models.py``)."""

    USER_CREATED = "user.created"
    USER_ROLES_CHANGED = "user.roles_changed"
    USER_ACTIVATED = "user.activated"
    USER_DEACTIVATED = "user.deactivated"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_DELETED = "user.deleted"
    CUSTOMER_ARCHIVED = "customer.archived"
    CUSTOMER_DELETED = "customer.deleted"
    PROJECT_ARCHIVED = "project.archived"
    PROJECT_DELETED = "project.deleted"
    BILLING_PERIOD_SENT = "billing_period.sent"
    BILLING_PERIOD_REOPENED = "billing_period.reopened"
    PUBLIC_HOLIDAYS_IMPORTED = "calendar.public_holidays_imported"
    BACKUP_CREATED = "backup.created"
    EXPENSE_REPORT_APPROVED = "expense_report.approved"
    EXPENSE_REPORT_RETURNED = "expense_report.returned"
    COMPANY_UPDATED = "company.updated"


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEventDTO:
    id: UUID
    occurred_at: datetime
    # Both `None` when the action had no signed-in actor (a CLI invocation, e.g. `create-admin` or
    # a scheduled `time-reporting backup`); `actor_name` is a snapshot taken at record time, so it
    # still reads correctly after the actor is renamed or (`actor_id` then `NULL`) deleted.
    actor_id: UUID | None
    actor_name: str | None
    action: AuditAction
    entity_type: str
    entity_id: str
    summary: str
    details: dict[str, Any] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEventPageDTO:
    items: tuple[AuditEventDTO, ...]
    total: int
    limit: int
    offset: int


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class ListAuditEvents(Query[AuditEventPageDTO]):
    """Newest first. Every filter is any-of-one (no repeated values) and optional."""

    limit: int
    offset: int
    action: AuditAction | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    actor_id: UUID | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordAuditEvent(Command[None]):
    """Write one event. Always executed as a nested command from within the owning module's own
    command handler — never call ``bus.execute`` on this directly from a router."""

    actor_id: UUID | None
    action: AuditAction
    entity_type: str
    entity_id: str
    summary: str
    details: dict[str, Any] | None = None
