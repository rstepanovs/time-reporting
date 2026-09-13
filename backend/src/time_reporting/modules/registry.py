"""Composition root of the CQRS bus: collects the handlers of every feature module."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.customers import module as customers_module
from time_reporting.modules.users import module as users_module


def build_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    users_module.register(registry)
    customers_module.register(registry)
    registry.freeze()
    return registry
