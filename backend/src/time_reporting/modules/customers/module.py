"""Registers the customers module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.customers.contracts import (
    CreateCustomer,
    GetCustomerById,
    ListCustomers,
    UpdateCustomer,
)
from time_reporting.modules.customers.handlers import (
    CreateCustomerHandler,
    GetCustomerByIdHandler,
    ListCustomersHandler,
    UpdateCustomerHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetCustomerById, GetCustomerByIdHandler)
    registry.query(ListCustomers, ListCustomersHandler)

    registry.command(CreateCustomer, CreateCustomerHandler)
    registry.command(UpdateCustomer, UpdateCustomerHandler)
