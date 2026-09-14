"""Command and query handlers of the customers module (registered in ``customers.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingPeriodDTO,
    CreateCustomer,
    CustomerDTO,
    CustomerPageDTO,
    DeleteCustomer,
    GetCustomerById,
    GetCustomersByIds,
    ListCustomers,
    UpdateCustomer,
)
from time_reporting.modules.customers.models import Customer
from time_reporting.modules.customers.repository import CustomerRepository
from time_reporting.modules.customers.service import CustomerService


def to_dto(customer: Customer) -> CustomerDTO:
    return CustomerDTO(
        id=customer.id,
        name=customer.name,
        legal_name=customer.legal_name,
        tax_id=customer.tax_id,
        billing_email=customer.billing_email,
        billing_address=BillingAddressDTO(
            line1=customer.billing_address_line1,
            line2=customer.billing_address_line2,
            city=customer.billing_city,
            region=customer.billing_region,
            postal_code=customer.billing_postal_code,
            country=customer.billing_country,
        ),
        billing_period=BillingPeriodDTO(
            interval_count=customer.billing_interval_count,
            interval_unit=customer.billing_interval_unit,
            anchor_date=customer.billing_anchor_date,
        ),
        currency=customer.currency,
        payment_terms_days=customer.payment_terms_days,
        notes=customer.notes,
        is_active=customer.is_active,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


# --- Queries ---


class _QueryHandler:
    def __init__(self, bus: Bus) -> None:
        self._customers = CustomerRepository(bus.session)


class GetCustomerByIdHandler(_QueryHandler):
    async def handle(self, query: GetCustomerById) -> CustomerDTO | None:
        customer = await self._customers.get_by_id(query.customer_id)
        return None if customer is None else to_dto(customer)


class GetCustomersByIdsHandler(_QueryHandler):
    async def handle(self, query: GetCustomersByIds) -> tuple[CustomerDTO, ...]:
        customers = await self._customers.get_by_ids(query.customer_ids)
        return tuple(to_dto(customer) for customer in customers)


class ListCustomersHandler(_QueryHandler):
    async def handle(self, query: ListCustomers) -> CustomerPageDTO:
        customers = await self._customers.get_page(
            limit=query.limit,
            offset=query.offset,
            include_inactive=query.include_inactive,
            search=query.search,
        )
        return CustomerPageDTO(
            items=tuple(to_dto(customer) for customer in customers),
            total=await self._customers.count(
                include_inactive=query.include_inactive, search=query.search
            ),
            limit=query.limit,
            offset=query.offset,
        )


# --- Commands ---


class _CommandHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = CustomerService(bus.session)


class CreateCustomerHandler(_CommandHandler):
    async def handle(self, command: CreateCustomer) -> CustomerDTO:
        return to_dto(await self._service.create_customer(command))


class UpdateCustomerHandler(_CommandHandler):
    async def handle(self, command: UpdateCustomer) -> CustomerDTO:
        return to_dto(await self._service.update_customer(command))


class DeleteCustomerHandler(_CommandHandler):
    async def handle(self, command: DeleteCustomer) -> None:
        await self._service.delete_customer(command.customer_id)
