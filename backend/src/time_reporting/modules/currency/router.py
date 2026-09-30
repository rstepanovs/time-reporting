"""Currency HTTP API: exchange-rate lookup for the accountant."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AccountantDep
from time_reporting.modules.currency.contracts import (
    ExchangeRateUnavailableError,
    GetExchangeRate,
)
from time_reporting.modules.currency.schemas import ExchangeRateResponse

router = APIRouter(prefix="/currency", tags=["currency"])

_UNAVAILABLE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_502_BAD_GATEWAY: {"description": "No rate published or the rates source is down"}
}


@router.get(
    "/rates/{currency}",
    response_model=ExchangeRateResponse,
    responses=_UNAVAILABLE_RESPONSE,
    summary="SEK per one unit of a currency on a date (latest published rate on or before it)",
)
async def get_rate(
    currency: Annotated[str, Path(pattern=r"^[A-Za-z]{3}$")],
    on: Annotated[date, Query()],
    bus: BusDep,
    _: AccountantDep,
) -> ExchangeRateResponse:
    try:
        rate = await bus.execute(GetExchangeRate(currency=currency, on_date=on))
    except ExchangeRateUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ExchangeRateResponse.model_validate(rate)
