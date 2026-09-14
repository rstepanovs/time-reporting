"""Composition root of the CQRS bus: collects the handlers of every feature module."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.admin import module as admin_module
from time_reporting.modules.customers import module as customers_module
from time_reporting.modules.projects import module as projects_module
from time_reporting.modules.users import module as users_module


def build_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    users_module.register(registry)
    customers_module.register(registry)
    projects_module.register(registry)
    admin_module.register(registry)
    registry.freeze()
    return registry
