"""Customers HTTP API: readable by any authenticated user, writable by managers."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import CurrentUserDep, ManagerDep
from time_reporting.modules.customers.contracts import (
    CLEARABLE_CUSTOMER_FIELDS,
    CreateCustomer,
    CustomerNameAlreadyExistsError,
    CustomerNotFoundError,
    GetCustomerById,
    ListCustomers,
    UpdateCustomer,
)
from time_reporting.modules.customers.schemas import (
    CustomerCreateRequest,
    CustomerPageResponse,
    CustomerResponse,
    CustomerUpdateRequest,
)

router = APIRouter(prefix="/customers", tags=["customers"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Customer not found"}
}
_NAME_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "A customer with this name already exists"}
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")


def _name_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="A customer with this name already exists"
    )


@router.get("")
async def list_customers(
    _user: CurrentUserDep,
    bus: BusDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_inactive: bool = False,
    search: Annotated[str | None, Query(max_length=255)] = None,
) -> CustomerPageResponse:
    page = await bus.query(
        ListCustomers(limit=limit, offset=offset, include_inactive=include_inactive, search=search)
    )
    return CustomerPageResponse.model_validate(page)


@router.post("", status_code=status.HTTP_201_CREATED, responses=_NAME_CONFLICT_RESPONSE)
async def create_customer(
    body: CustomerCreateRequest, _manager: ManagerDep, bus: BusDep
) -> CustomerResponse:
    try:
        customer = await bus.execute(
            CreateCustomer(
                name=body.name,
                legal_name=body.legal_name,
                tax_id=body.tax_id,
                billing_email=body.billing_email,
                billing_address=body.billing_address.to_dto(),
                billing_period=body.billing_period.to_dto(),
                currency=body.currency,
                payment_terms_days=body.payment_terms_days,
                notes=body.notes,
            )
        )
    except CustomerNameAlreadyExistsError as exc:
        raise _name_conflict() from exc
    return CustomerResponse.model_validate(customer)


@router.get("/{customer_id}", responses=_NOT_FOUND_RESPONSE)
async def read_customer(customer_id: UUID, _user: CurrentUserDep, bus: BusDep) -> CustomerResponse:
    customer = await bus.query(GetCustomerById(customer_id=customer_id))
    if customer is None:
        raise _not_found()
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}", responses={**_NOT_FOUND_RESPONSE, **_NAME_CONFLICT_RESPONSE})
async def update_customer(
    customer_id: UUID, body: CustomerUpdateRequest, _manager: ManagerDep, bus: BusDep
) -> CustomerResponse:
    # An explicit null (as opposed to an omitted field) clears an optional text field.
    clear_fields = frozenset(
        name
        for name in CLEARABLE_CUSTOMER_FIELDS
        if name in body.model_fields_set and getattr(body, name) is None
    )
    try:
        customer = await bus.execute(
            UpdateCustomer(
                customer_id=customer_id,
                name=body.name,
                legal_name=body.legal_name,
                tax_id=body.tax_id,
                billing_email=body.billing_email,
                billing_address=(
                    None if body.billing_address is None else body.billing_address.to_dto()
                ),
                billing_period=(
                    None if body.billing_period is None else body.billing_period.to_dto()
                ),
                currency=body.currency,
                payment_terms_days=body.payment_terms_days,
                notes=body.notes,
                is_active=body.is_active,
                clear_fields=clear_fields,
            )
        )
    except CustomerNotFoundError as exc:
        raise _not_found() from exc
    except CustomerNameAlreadyExistsError as exc:
        raise _name_conflict() from exc
    return CustomerResponse.model_validate(customer)
