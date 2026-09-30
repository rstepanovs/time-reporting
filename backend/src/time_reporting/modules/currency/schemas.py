"""HTTP response models of the currency API."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ExchangeRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    requested_date: date
    rate_date: date
    rate: Decimal
    source: str
