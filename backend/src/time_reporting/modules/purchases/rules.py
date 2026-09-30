"""Per-kind validation of ``PurchaseDetails`` — pure, no I/O."""

from dataclasses import replace
from decimal import Decimal

from time_reporting.modules.currency.contracts import CURRENCY_CODE_PATTERN
from time_reporting.modules.purchases.contracts import (
    PaymentMethod,
    PaymentStatus,
    PurchaseDetails,
    PurchaseKind,
    PurchaseValidationError,
)


def _require(details: PurchaseDetails, *names: str) -> None:
    missing = [name for name in names if getattr(details, name) is None]
    if missing:
        raise PurchaseValidationError(
            f"A {details.kind.value.replace('_', ' ')} needs: {', '.join(missing)}"
        )


def _forbid(details: PurchaseDetails, *names: str) -> None:
    present = [name for name in names if getattr(details, name) is not None]
    if present:
        raise PurchaseValidationError(
            f"A {details.kind.value.replace('_', ' ')} can't have: {', '.join(present)}"
        )


def normalize(details: PurchaseDetails) -> PurchaseDetails:
    """Validate ``details`` against the rules of its kind and return it normalized (upper-case
    currency; a receipt's implied payment fields filled in). Raises ``PurchaseValidationError``."""
    if details.currency is not None:
        currency = details.currency.upper()
        if CURRENCY_CODE_PATTERN.fullmatch(currency) is None:
            raise PurchaseValidationError(f"{currency!r} is not a currency code")
        details = replace(details, currency=currency)
    if details.amount is not None and details.amount <= Decimal(0):
        raise PurchaseValidationError("The amount must be positive")
    if details.vat_amount is not None and details.vat_amount < Decimal(0):
        raise PurchaseValidationError("The VAT amount can't be negative")
    if details.amount_base is not None and details.exchange_rate is not None:
        raise PurchaseValidationError("Give either a base-currency amount or an exchange rate")
    if details.amount_base is not None and details.amount_base <= Decimal(0):
        raise PurchaseValidationError("The base-currency amount must be positive")
    if details.exchange_rate is not None and details.exchange_rate <= Decimal(0):
        raise PurchaseValidationError("The exchange rate must be positive")

    match details.kind:
        case PurchaseKind.RECEIPT:
            _require(details, "document_date", "amount", "currency", "payment_method")
            _forbid(details, "due_date")
            if details.payment_status is PaymentStatus.UNPAID:
                raise PurchaseValidationError("A receipt is always paid")
            return replace(
                details,
                payment_status=PaymentStatus.PAID,
                paid_on=details.paid_on or details.document_date,
            )
        case PurchaseKind.INVOICE | PurchaseKind.CARD_INVOICE:
            _require(details, "document_date", "amount", "currency", "payment_status")
            if (
                details.kind is PurchaseKind.CARD_INVOICE
                and details.payment_method is PaymentMethod.CARD
            ):
                raise PurchaseValidationError("A card invoice can't be paid by card")
            if details.payment_status is PaymentStatus.UNPAID:
                _require(details, "due_date")
                _forbid(details, "paid_on", "payment_method")
            else:
                _require(details, "paid_on", "payment_method")
            return details
        case PurchaseKind.OTHER:
            _forbid(
                details,
                "due_date",
                "payment_status",
                "paid_on",
                "payment_method",
                "amount",
                "currency",
                "vat_amount",
                "amount_base",
                "exchange_rate",
            )
            return details
