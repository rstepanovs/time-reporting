"""Customer domain logic on ORM entities.

Changes are flushed through the repository; the bus commits.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.customers.contracts import (
    CLEARABLE_CUSTOMER_FIELDS,
    BillingAddressDTO,
    BillingPeriodDTO,
    CreateCustomer,
    CustomerNameAlreadyExistsError,
    CustomerNotFoundError,
    UpdateCustomer,
)
from time_reporting.modules.customers.models import Customer
from time_reporting.modules.customers.repository import CustomerRepository


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self._customers = CustomerRepository(session)

    async def get_customer(self, customer_id: UUID) -> Customer:
        customer = await self._customers.get_by_id(customer_id)
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        return customer

    async def create_customer(self, data: CreateCustomer) -> Customer:
        await self._ensure_name_available(data.name)
        customer = Customer(
            name=data.name,
            legal_name=data.legal_name,
            tax_id=data.tax_id,
            billing_email=data.billing_email,
            currency=data.currency.upper(),
            payment_terms_days=data.payment_terms_days,
            notes=data.notes,
        )
        _set_billing_address(customer, data.billing_address)
        _set_billing_period(customer, data.billing_period)
        await self._customers.save(customer)
        return customer

    async def update_customer(self, data: UpdateCustomer) -> Customer:
        customer = await self.get_customer(data.customer_id)

        if data.name is not None and data.name != customer.name:
            await self._ensure_name_available(data.name)
            customer.name = data.name
        for field_name in CLEARABLE_CUSTOMER_FIELDS:
            if field_name in data.clear_fields:
                setattr(customer, field_name, None)
            elif (value := getattr(data, field_name)) is not None:
                setattr(customer, field_name, value)
        if data.billing_address is not None:
            _set_billing_address(customer, data.billing_address)
        if data.billing_period is not None:
            _set_billing_period(customer, data.billing_period)
        if data.currency is not None:
            customer.currency = data.currency.upper()
        if data.payment_terms_days is not None:
            customer.payment_terms_days = data.payment_terms_days
        if data.is_active is not None:
            customer.is_active = data.is_active
        await self._customers.save(customer)
        return customer

    async def delete_customer(self, customer_id: UUID) -> None:
        await self._customers.delete(await self.get_customer(customer_id))

    async def _ensure_name_available(self, name: str) -> None:
        if await self._customers.get_by_name(name) is not None:
            raise CustomerNameAlreadyExistsError(name)


def _set_billing_address(customer: Customer, address: BillingAddressDTO) -> None:
    customer.billing_address_line1 = address.line1
    customer.billing_address_line2 = address.line2
    customer.billing_city = address.city
    customer.billing_region = address.region
    customer.billing_postal_code = address.postal_code
    customer.billing_country = address.country.upper()


def _set_billing_period(customer: Customer, period: BillingPeriodDTO) -> None:
    customer.billing_interval_count = period.interval_count
    customer.billing_interval_unit = period.interval_unit
    customer.billing_anchor_date = period.anchor_date
