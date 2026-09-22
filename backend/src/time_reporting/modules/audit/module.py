"""Registers the audit module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.audit.contracts import ListAuditEvents, RecordAuditEvent
from time_reporting.modules.audit.handlers import ListAuditEventsHandler, RecordAuditEventHandler


def register(registry: HandlerRegistry) -> None:
    registry.command(RecordAuditEvent, RecordAuditEventHandler)
    registry.query(ListAuditEvents, ListAuditEventsHandler)
