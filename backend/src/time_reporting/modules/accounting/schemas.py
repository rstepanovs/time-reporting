"""HTTP response models of the accounting API. ``BuildAccountantPackage``'s result is streamed
back as a raw file, not one of these — see ``router.py``."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountantPackageTotalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    invoiced_total: Decimal
    expense_total: Decimal


class AccountantPackageStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    invoice_count: int
    expense_line_count: int
    totals: list[AccountantPackageTotalResponse]
    draft_invoice_count: int
    unapproved_expense_report_count: int
    uninvoiced_sent_period_count: int
