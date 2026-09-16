"""Registers the system module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.system.contracts import GetSystemConfig, GetSystemStatus
from time_reporting.modules.system.handlers import GetSystemConfigHandler, GetSystemStatusHandler


def register(registry: HandlerRegistry) -> None:
    registry.query(GetSystemStatus, GetSystemStatusHandler)
    registry.query(GetSystemConfig, GetSystemConfigHandler)
