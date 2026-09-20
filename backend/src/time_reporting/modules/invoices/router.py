"""Invoices HTTP API. Every route requires the ``accountant`` level."""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AccountantDep
from time_reporting.modules.invoices.contracts import (
    BillingItemRateMissingError,
    CompanyProfileIncompleteError,
    CreateInvoiceDraft,
    DeleteInvoiceDraft,
    GetInvoice,
    GetInvoicePdf,
    InvoiceCustomerNotFoundError,
    InvoiceEmptyError,
    InvoiceLineChange,
    InvoiceLineNotFoundError,
    InvoiceNoPeriodsError,
    InvoiceNotDraftError,
    InvoiceNotFoundError,
    InvoiceNotIssuedError,
    InvoiceNotVoidableError,
    InvoicePeriodNotEligibleError,
    InvoiceStatus,
    IssueInvoice,
    ListInvoiceablePeriods,
    ListInvoices,
    MarkInvoicePaid,
    UpdateInvoiceDraft,
    VoidInvoice,
)
from time_reporting.modules.invoices.schemas import (
    CreateInvoiceDraftRequest,
    InvoiceableCustomerResponse,
    InvoicePageResponse,
    InvoiceResponse,
    MarkInvoicePaidRequest,
    UpdateInvoiceDraftRequest,
    VoidInvoiceRequest,
)
from time_reporting.modules.timesheets.contracts import BillingPeriodRef

router = APIRouter(prefix="/invoices", tags=["invoices"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Invoice not found"}
}
_RULE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "The draft violates an invoicing rule"}
}
_STATUS_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "The invoice is not a draft"}
}


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("/invoiceable-periods")
async def list_invoiceable_periods(
    _accountant: AccountantDep, bus: BusDep
) -> list[InvoiceableCustomerResponse]:
    customers = await bus.query(ListInvoiceablePeriods())
    return [InvoiceableCustomerResponse.model_validate(customer) for customer in customers]


@router.get("")
async def list_invoices(
    _accountant: AccountantDep,
    bus: BusDep,
    customer_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvoicePageResponse:
    page = await bus.query(
        ListInvoices(
            customer_id=customer_id,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    )
    return InvoicePageResponse.model_validate(page)


@router.post("", status_code=status.HTTP_201_CREATED, responses=_RULE_RESPONSE)
async def create_invoice_draft(
    body: CreateInvoiceDraftRequest, current_user: AccountantDep, bus: BusDep
) -> InvoiceResponse:
    periods = tuple(
        BillingPeriodRef(project_id=period.project_id, period_start=period.period_start)
        for period in body.periods
    )
    try:
        invoice = await bus.execute(
            CreateInvoiceDraft(
                customer_id=body.customer_id,
                periods=periods,
                invoice_date=date.today(),
                actor_id=current_user.id,
            )
        )
    except InvoiceCustomerNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except (
        InvoiceNoPeriodsError,
        InvoicePeriodNotEligibleError,
        BillingItemRateMissingError,
    ) as exc:
        raise _bad_request(str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)


@router.get("/{invoice_id}", responses=_NOT_FOUND_RESPONSE)
async def get_invoice(invoice_id: UUID, _accountant: AccountantDep, bus: BusDep) -> InvoiceResponse:
    try:
        invoice = await bus.query(GetInvoice(invoice_id=invoice_id))
    except InvoiceNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)


@router.put(
    "/{invoice_id}",
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def update_invoice_draft(
    invoice_id: UUID, body: UpdateInvoiceDraftRequest, current_user: AccountantDep, bus: BusDep
) -> InvoiceResponse:
    lines = tuple(
        InvoiceLineChange(
            line_id=change.line_id,
            description=change.description,
            quantity=change.quantity,
            unit=change.unit,
            unit_price=change.unit_price,
        )
        for change in body.lines
    )
    try:
        invoice = await bus.execute(
            UpdateInvoiceDraft(
                invoice_id=invoice_id,
                actor_id=current_user.id,
                invoice_date=body.invoice_date,
                due_date=body.due_date,
                vat_rate=body.vat_rate,
                vat_note=body.vat_note,
                your_reference=body.your_reference,
                notes=body.notes,
                lines=lines,
                delete_line_ids=frozenset(body.delete_line_ids),
                clear_fields=frozenset(body.clear_fields),
            )
        )
    except (InvoiceNotFoundError, InvoiceLineNotFoundError) as exc:
        raise _not_found(str(exc)) from exc
    except InvoiceNotDraftError as exc:
        raise _conflict(str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)


@router.delete(
    "/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def delete_invoice_draft(invoice_id: UUID, current_user: AccountantDep, bus: BusDep) -> None:
    try:
        await bus.execute(DeleteInvoiceDraft(invoice_id=invoice_id, actor_id=current_user.id))
    except InvoiceNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except InvoiceNotDraftError as exc:
        raise _conflict(str(exc)) from exc


@router.post(
    "/{invoice_id}/issue",
    responses={**_NOT_FOUND_RESPONSE, **_RULE_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def issue_invoice(
    invoice_id: UUID, current_user: AccountantDep, bus: BusDep
) -> InvoiceResponse:
    try:
        invoice = await bus.execute(IssueInvoice(invoice_id=invoice_id, actor_id=current_user.id))
    except InvoiceNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except (InvoiceEmptyError, CompanyProfileIncompleteError) as exc:
        raise _bad_request(str(exc)) from exc
    except InvoiceNotDraftError as exc:
        raise _conflict(str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)


@router.post(
    "/{invoice_id}/pay",
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def mark_invoice_paid(
    invoice_id: UUID, body: MarkInvoicePaidRequest, current_user: AccountantDep, bus: BusDep
) -> InvoiceResponse:
    try:
        invoice = await bus.execute(
            MarkInvoicePaid(invoice_id=invoice_id, actor_id=current_user.id, paid_on=body.paid_on)
        )
    except InvoiceNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except InvoiceNotIssuedError as exc:
        raise _conflict(str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)


@router.post(
    "/{invoice_id}/void",
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def void_invoice(
    invoice_id: UUID, body: VoidInvoiceRequest, current_user: AccountantDep, bus: BusDep
) -> InvoiceResponse:
    try:
        invoice = await bus.execute(
            VoidInvoice(invoice_id=invoice_id, actor_id=current_user.id, reason=body.reason)
        )
    except InvoiceNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except InvoiceNotVoidableError as exc:
        raise _conflict(str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)


@router.get("/{invoice_id}/pdf", responses=_NOT_FOUND_RESPONSE)
async def get_invoice_pdf(invoice_id: UUID, _accountant: AccountantDep, bus: BusDep) -> Response:
    try:
        pdf = await bus.query(GetInvoicePdf(invoice_id=invoice_id))
    except InvoiceNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    return Response(
        content=pdf.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf.filename}"'},
    )
