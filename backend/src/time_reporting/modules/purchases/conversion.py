"""Conversion of a document's amount into the company's base currency.

Rules (see ``.claude/plans/email-integration.md``, "Riksbank rates of the payment date"):

- Already in the base currency: the amount as is, no rate.
- A paid document uses the rate of ``paid_on`` and is final; an unpaid one a *provisional* rate of
  its document date.
- A card payment (except a card invoice itself) is never converted: the real amount comes from the
  card invoice's line, typed in when the receipt is linked to it.
- A manual amount or rate, and an amount taken from a card invoice, are never recomputed.
- A currency without a published rate leaves the amount empty for the user to type in.
"""

from decimal import ROUND_HALF_UP, Decimal

from time_reporting.core.cqrs import Bus
from time_reporting.modules.company.contracts import GetCompanySettings
from time_reporting.modules.currency.contracts import (
    ExchangeRateUnavailableError,
    GetExchangeRate,
)
from time_reporting.modules.purchases.contracts import (
    PaymentMethod,
    PaymentStatus,
    PurchaseKind,
    RateSource,
)
from time_reporting.modules.purchases.models import PurchaseDocument

_CENT = Decimal("0.01")
_RATE_PLACES = Decimal("0.00000001")

# Sources a recompute must leave alone.
_KEPT_SOURCES = frozenset({RateSource.MANUAL, RateSource.CARD_INVOICE})


def is_converted_by_hand(document: PurchaseDocument) -> bool:
    return document.rate_source in _KEPT_SOURCES


def _clear(document: PurchaseDocument) -> None:
    document.amount_base = None
    document.exchange_rate = None
    document.rate_date = None
    document.rate_source = None
    document.amount_base_final = False


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


class Converter:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def apply(
        self,
        document: PurchaseDocument,
        *,
        manual_amount_base: Decimal | None = None,
        manual_rate: Decimal | None = None,
        recompute: bool = False,
    ) -> None:
        """Set the conversion fields of ``document`` from its amount, currency, payment state and
        the overrides. ``recompute`` also discards a manual conversion (never a card invoice's)."""
        paid = document.payment_status is PaymentStatus.PAID

        if (
            document.kind is None
            or document.kind is PurchaseKind.OTHER
            or (document.amount is None or document.currency is None)
        ):
            _clear(document)
            return

        if manual_amount_base is not None:
            document.amount_base = _round_money(manual_amount_base)
            document.exchange_rate = (manual_amount_base / document.amount).quantize(_RATE_PLACES)
            document.rate_date = None
            document.rate_source = RateSource.MANUAL
            document.amount_base_final = paid
            return
        if manual_rate is not None:
            document.amount_base = _round_money(document.amount * manual_rate)
            document.exchange_rate = manual_rate
            document.rate_date = None
            document.rate_source = RateSource.MANUAL
            document.amount_base_final = paid
            return

        if document.rate_source is RateSource.CARD_INVOICE:
            return
        if document.rate_source is RateSource.MANUAL and not recompute:
            document.amount_base_final = paid
            return

        if (
            document.payment_method is PaymentMethod.CARD
            and document.kind is not PurchaseKind.CARD_INVOICE
        ):
            _clear(document)
            return

        base_currency = (await self._bus.query(GetCompanySettings())).base_currency
        if document.currency == base_currency:
            document.amount_base = document.amount
            document.exchange_rate = Decimal(1)
            document.rate_date = None
            document.rate_source = RateSource.NONE
            document.amount_base_final = paid
            return

        rate_on = document.paid_on if paid else document.document_date
        if rate_on is None:
            _clear(document)
            return
        try:
            rate = await self._bus.execute(
                GetExchangeRate(currency=document.currency, on_date=rate_on)
            )
        except ExchangeRateUnavailableError:
            _clear(document)
            return
        document.amount_base = _round_money(document.amount * rate.rate)
        document.exchange_rate = rate.rate
        document.rate_date = rate.rate_date
        document.rate_source = RateSource.RIKSBANK
        document.amount_base_final = paid
