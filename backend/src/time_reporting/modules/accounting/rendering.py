"""Renders the accountant package's ``summary.pdf`` via Jinja2 + WeasyPrint.

Unlike ``invoices/rendering.py`` (which delegates the whole render to ``faktura-printer``), the
monthly summary has its own shape — a company header, then an invoices table, then an expenses
table split rebilled/internal, then per-currency totals — with nothing to reuse from a single
invoice's layout, so this module owns a small inline template directly.
"""

import asyncio
from decimal import Decimal
from typing import cast

from jinja2 import Environment
from weasyprint import HTML

from time_reporting.modules.accounting.content import PackageContent
from time_reporting.modules.company.contracts import CompanySettingsDTO

_TEMPLATE_SOURCE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page { size: A4; margin: 18mm 14mm; }
  body { font-family: sans-serif; font-size: 9.5pt; color: #111; }
  h1 { font-size: 15pt; margin-bottom: 2pt; }
  h2 { font-size: 11pt; margin-top: 16pt; margin-bottom: 4pt; }
  .subtitle { color: #555; margin-bottom: 14pt; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 8pt; }
  th, td { text-align: left; padding: 3pt 5pt; border-bottom: 1px solid #ddd; }
  th { border-bottom: 1px solid #333; font-weight: bold; }
  td.num, th.num { text-align: right; white-space: nowrap; }
  .empty { color: #777; font-style: italic; }
  .group-heading { font-weight: bold; padding-top: 6pt; }
</style>
</head>
<body>
  <h1>{{ company.legal_name }}</h1>
  <div class="subtitle">Accountant package — {{ month_name }} {{ content.year }}</div>

  <h2>Invoices</h2>
  {% if content.invoices %}
  <table>
    <thead>
      <tr>
        <th>Number</th><th>Date</th><th>Customer</th>
        <th class="num">Net</th><th class="num">VAT</th><th class="num">Total</th><th>Status</th>
      </tr>
    </thead>
    <tbody>
      {% for row in content.invoices %}
      <tr>
        <td>{{ row.number }}</td>
        <td>{{ row.invoice_date }}</td>
        <td>{{ row.customer_name }}</td>
        <td class="num">{{ row.net | money }} {{ row.currency }}</td>
        <td class="num">{{ row.vat | money }} {{ row.currency }}</td>
        <td class="num">{{ row.total | money }} {{ row.currency }}</td>
        <td>{{ row.status }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">No invoices this month.</p>
  {% endif %}

  <h2>Expenses</h2>
  {% if content.expense_rows %}
  <table>
    <thead>
      <tr>
        <th>Date</th><th>Employee</th><th>Project</th><th>Vendor</th><th>Doc. no.</th>
        <th>Description</th><th class="num">Amount</th><th>Receipt</th>
      </tr>
    </thead>
    <tbody>
      <tr><td colspan="8" class="group-heading">Rebilled to customers</td></tr>
      {% for row in rebilled_rows %}
      <tr>
        <td>{{ row.expense_date }}</td>
        <td>{{ row.employee_name }}</td>
        <td>{{ row.project_name }}</td>
        <td>{{ row.vendor }}</td>
        <td>{{ row.document_no }}</td>
        <td>{{ row.description }}</td>
        <td class="num">{{ row.amount | money }} {{ row.currency }}</td>
        <td>{{ row.receipt_numbers | receipts }}</td>
      </tr>
      {% else %}
      <tr><td colspan="8" class="empty">None</td></tr>
      {% endfor %}
      <tr><td colspan="8" class="group-heading">Internal costs (never billed)</td></tr>
      {% for row in internal_rows %}
      <tr>
        <td>{{ row.expense_date }}</td>
        <td>{{ row.employee_name }}</td>
        <td>{{ row.project_name }}</td>
        <td>{{ row.vendor }}</td>
        <td>{{ row.document_no }}</td>
        <td>{{ row.description }}</td>
        <td class="num">{{ row.amount | money }} {{ row.currency }}</td>
        <td>{{ row.receipt_numbers | receipts }}</td>
      </tr>
      {% else %}
      <tr><td colspan="8" class="empty">None</td></tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">No expenses this month.</p>
  {% endif %}

  <h2>Totals</h2>
  {% if content.totals %}
  <table>
    <thead>
      <tr><th>Currency</th><th class="num">Invoiced</th><th class="num">Expenses</th></tr>
    </thead>
    <tbody>
      {% for total in content.totals %}
      <tr>
        <td>{{ total.currency }}</td>
        <td class="num">{{ total.invoiced_total | money }}</td>
        <td class="num">{{ total.expense_total | money }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">Nothing to total.</p>
  {% endif %}
</body>
</html>
"""

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


def _money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ")


def _receipts(numbers: tuple[int, ...]) -> str:
    return ", ".join(f"{number:03d}" for number in numbers) if numbers else "—"


_env = Environment(autoescape=True)
_env.filters["money"] = _money
_env.filters["receipts"] = _receipts
_template = _env.from_string(_TEMPLATE_SOURCE)


def _render(content: PackageContent, *, company: CompanySettingsDTO) -> bytes:
    html = _template.render(
        content=content,
        company=company,
        month_name=_MONTH_NAMES[content.month - 1],
        rebilled_rows=[row for row in content.expense_rows if not row.is_internal],
        internal_rows=[row for row in content.expense_rows if row.is_internal],
    )
    return cast(bytes, HTML(string=html).write_pdf())


async def render_summary_pdf(content: PackageContent, *, company: CompanySettingsDTO) -> bytes:
    """Render ``summary.pdf``. WeasyPrint is CPU-bound, so the actual render runs in a thread —
    the same pattern ``invoices.rendering.render_invoice_pdf`` uses."""
    return await asyncio.to_thread(_render, content, company=company)
