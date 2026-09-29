"""Our own visual theme for issued/draft invoice PDFs, adapted from `faktura-printer`'s bundled
"classic" theme: a total/due-date line in the header, references trimmed to only the fields our
app ever fills in (see ``_build_invoice`` — most of `InvoiceInfo`'s fields are never set), and a
muted graphite accent (`_ACCENT`) used only for hairline rules and text, never a solid fill — three
deliberate departures from the bundled theme, all requested in review:

1. No enclosing boxes (the bundled theme's `.items-frame`/`.amount-due` borders) around content
   that can grow or straddle a page break — a border on an element that breaks across pages only
   draws at the very top of the first fragment and bottom of the last, which looks broken rather
   than protective. Section separation is border-top/border-bottom rules instead, which have
   nothing to "break": they repeat on their own row/edge regardless of how tall the content is.
2. The references block (`.refs`) only prints a row for a field that actually has a value, instead
   of a fixed 4-column grid with blank cells wherever `InvoiceInfo` wasn't populated; the due date
   is dropped from it entirely since the header line already shows it once. The notes box is
   likewise omitted entirely when there's no note, rather than printing an empty bordered box.
3. `_ACCENT` is a moderate charcoal (`#3a3a3a`), applied as text/border color; nothing is a solid
   accent-filled block (contrast the bundled "modern" theme's solid-teal table header).

`faktura_printer.Design.template`/`.css` only accept a *file path*, never raw text (see
`renderer._read_design_asset`), and `rendering.py` renders in `untrusted=True` mode (see its own
docstring for why) — that mode requires a real `base_dir` and resolves `template`/`css` as bare
file names inside it. So this module writes its two strings to a temp directory once, at import
time (the backend process is long-lived, so "once per process" is "once, ever"), and exposes that
directory for `rendering.py` to pass as `base_dir`.
"""

import tempfile
from pathlib import Path

TEMPLATE_FILENAME = "invoice.html.j2"
CSS_FILENAME = "custom.css"
_TEMPLATE = r"""{%- set s = inv.seller -%}
{%- set b = inv.buyer -%}
{%- set i = inv.invoice -%}
{%- set t = inv.totals -%}
{%- set vat_amount_label = (L.vat_amount_base ~ " " ~ i.currency) if i.currency else L.vat_amount -%}
{%- set total_label = (L.total_base ~ " " ~ i.currency) if i.currency else L.total -%}

{%- macro address_lines(addr) -%}
  {%- if addr.care_of %}<div>&#8453; {{ addr.care_of }}</div>{% endif -%}
  {%- if addr.street %}<div class="multiline">{{ addr.street }}</div>{% endif -%}
  {%- if addr.postal_code or addr.city -%}
    <div>{{ addr.postal_code }}{% if addr.postal_code and addr.city %}&nbsp;&nbsp;{% endif %}{{ addr.city }}</div>
  {%- endif -%}
  {%- if addr.country %}<div>{{ addr.country }}</div>{% endif -%}
{%- endmacro -%}

{%- macro footer_field(label, value) -%}
  {%- if value %}<div class="footer-field"><div class="footer-label">{{ label }}</div><div>{{ value }}</div></div>{% endif -%}
{%- endmacro -%}

{%- macro ref_row(label, value) -%}
  {%- if value %}<tr><td class="ref-label">{{ label }}</td><td class="ref-value">{{ value }}</td></tr>{% endif -%}
{%- endmacro -%}

<!doctype html>
<html lang="{{ lang }}">
<head>
<meta charset="utf-8">
<title>{{ L.title }} {{ i.number }}</title>
<style>
{{ css }}
</style>
</head>
<body>

<table class="head">
  <tr>
    <td class="logo-cell">
      {%- if logo_src %}
      <img class="logo" src="{{ logo_src }}" alt="{{ s.name }}">
      {%- else %}
      <div class="seller-name">{{ s.name }}</div>
      {%- endif %}
    </td>
    <td>
      <h1>{{ L.title }}</h1>
      <table class="meta">
        <tr>
          <th>{{ L.invoice_customer_number }}</th>
          <th>{{ L.invoice_date }}</th>
        </tr>
        <tr>
          <td>{{ i.number }}{% if i.customer_number %}&nbsp;/&nbsp;&nbsp;&nbsp;&nbsp;{{ i.customer_number }}{% endif %}</td>
          <td>{{ date(i.date) }}</td>
        </tr>
      </table>
      <div class="buyer">
        <div class="name">{{ b.name }}</div>
        {{ address_lines(b.address) }}
        {%- if b.org_number %}<div>{{ L.org_number }} {{ b.org_number }}</div>{% endif -%}
        {%- if b.vat_number %}<div>{{ L.vat_number }} {{ b.vat_number }}</div>{% endif -%}
      </div>
    </td>
  </tr>
</table>

<table class="amount-due">
  <tr>
    <td class="amount-due-label">{{ total_label }}</td>
    <td class="amount-due-label">{{ L.due_date }}</td>
  </tr>
  <tr>
    <td class="amount-due-value">{{ money(t.total) }}</td>
    <td class="amount-due-value">{{ date(i.due_date) }}</td>
  </tr>
</table>

<table class="refs">
  {{ ref_row(L.your_reference, i.your_reference) }}
  {{ ref_row(L.our_reference, i.our_reference) }}
  {{ ref_row(L.your_order_number, i.your_order_number) }}
  {{ ref_row(L.payment_terms, i.payment_terms) }}
  {{ ref_row(L.delivery_terms, i.delivery_terms) }}
  {{ ref_row(L.delivery_method, i.delivery_method) }}
  {{ ref_row(L.late_interest, i.late_interest) }}
</table>

<table class="items">
  <colgroup>
    <col style="width: 20mm">
    <col>
    <col style="width: 25mm">
    <col style="width: 21mm">
    <col style="width: 28mm">
  </colgroup>
  <thead>
    <tr>
      <th>{{ L.article_number }}</th>
      <th>{{ L.description }}</th>
      <th>{{ L.quantity_unit }}</th>
      <th class="num">{{ L.unit_price }}</th>
      <th class="num">{{ L.amount }}</th>
    </tr>
  </thead>
  <tbody>
    {%- for item in inv.items %}
    <tr>
      <td>{{ item.article_number }}</td>
      <td class="multiline">{{ item.description }}</td>
      <td>{{ number(item.quantity) }}{% if item.unit %} {{ item.unit }}{% endif %}</td>
      <td class="num">{{ money(item.unit_price) }}</td>
      <td class="num">{{ money(item.amount) }}</td>
    </tr>
    {%- endfor %}
  </tbody>
</table>

<table class="totals">
  <colgroup>
    <col style="width: 27%">
    <col style="width: 17%">
    <col style="width: 23%">
    <col style="width: 33%">
  </colgroup>
  <tr>
    <th class="num">{{ L.excl_vat }}</th>
    <th class="num">{{ L.vat_rate }}</th>
    <th class="num">{{ vat_amount_label }}</th>
    <th class="num grand">{{ total_label }}</th>
  </tr>
  <tr>
    <td class="num">{{ money(t.excl_vat) }}</td>
    <td class="num">{{ number(t.vat_rate) }}</td>
    <td class="num">{{ money(t.vat_amount) }}</td>
    <td class="num grand">{{ money(t.total) }}</td>
  </tr>
</table>

{%- if inv.notes %}
<div class="notes">{{ inv.notes }}</div>
{%- endif %}

<table class="footer">
  <tr>
    <td class="footer-col footer-col-wide">
      {{ footer_field(L.org_number, s.org_number) }}
      {{ footer_field(L.vat_number, s.vat_number) }}
      {%- if s.f_tax_approved %}
      <div class="footer-field">{{ L.f_tax_approved }}</div>
      {%- endif %}
      {{ footer_field(L.bankgiro, s.bankgiro) }}
      {{ footer_field(L.iban, s.iban) }}
      {{ footer_field(L.bic, s.bic) }}
    </td>
    <td class="footer-col">
      {{ footer_field(L.registered_office, s.registered_office) }}
      <div class="footer-field">
        <div class="footer-label">{{ L.address }}</div>
        {{ address_lines(s.address) }}
      </div>
    </td>
    <td class="footer-col">
      {{ footer_field(L.phone, s.phone) }}
      {%- if s.email %}
      <div class="footer-field">
        <div class="footer-label">{{ L.email }}</div>
        <div><a href="mailto:{{ s.email }}">{{ s.email }}</a></div>
      </div>
      {%- endif %}
    </td>
  </tr>
</table>

</body>
</html>
"""

# A moderate charcoal, used only for text and hairline rules — never a solid fill (see the module
# docstring's point 3). `_RULE` is a lighter neutral gray for separators that are structural rather
# than meaningful (e.g. the footer's top border), so the page has one clear accent, not two.
_ACCENT = "#3a3a3a"
_RULE = "#d6d6d6"
_MUTED = "#6b6b6b"
_FOOTER_SIZE = "7pt"
_FOOTER_LABEL_SIZE = "6pt"

_CSS = f"""
@page {{
  size: A4;
  margin: 22mm 20mm 18mm 25mm;
}}

html {{
  font-family: "Liberation Sans", Arial, Helvetica, sans-serif;
  font-size: 9.5pt;
  color: #000;
}}

body {{
  margin: 0;
}}

table {{
  border-collapse: collapse;
  width: 100%;
}}

th,
td {{
  padding: 0;
  text-align: left;
  vertical-align: top;
  font-weight: normal;
}}

.num {{
  text-align: right;
  white-space: nowrap;
}}

.multiline {{
  white-space: pre-line;
}}

/* Header: logo on the left, title, invoice box and buyer on the right */
.head td.logo-cell {{
  width: 77.5mm;
}}

.logo {{
  display: block;
  width: 62mm;
  max-height: 32mm;
  object-fit: contain;
  object-position: left top;
  margin-top: 4mm;
}}

.seller-name {{
  margin-top: 6mm;
  font-size: 16pt;
  font-weight: bold;
}}

h1 {{
  margin: 3.5mm 0 3mm;
  font-size: 13pt;
  font-weight: bold;
}}

/* A plain label/value pair, no enclosing box — reused by .meta, .refs and .amount-due */
.meta th {{
  width: 50%;
  padding-bottom: 1mm;
  font-size: 7.5pt;
  font-weight: normal;
  text-transform: uppercase;
  letter-spacing: 0.3pt;
  color: {_MUTED};
}}

.meta td {{
  width: 50%;
}}

.buyer {{
  margin-top: 5mm;
  font-size: 11pt;
}}

.buyer .name {{
  margin-bottom: 4mm;
}}

/* Total/due-date line, right after the header — a rule, not a box, so it can't look "broken" if
   it ever had to straddle a page break */
.amount-due {{
  margin-top: 7mm;
  padding: 2.5mm 0;
  border-top: 0.75pt solid {_ACCENT};
  border-bottom: 0.75pt solid {_ACCENT};
  break-inside: avoid;
}}

.amount-due td {{
  width: 50%;
}}

.amount-due-label {{
  font-size: 7.5pt;
  text-transform: uppercase;
  letter-spacing: 0.3pt;
  color: {_MUTED};
}}

.amount-due-value {{
  padding-top: 0.5mm;
  font-size: 14pt;
  font-weight: bold;
  color: {_ACCENT};
}}

/* References: one row per field that actually has a value (see ref_row in the template) — no
   fixed grid of mostly-blank cells */
.refs {{
  margin-top: 7mm;
}}

.refs .ref-label {{
  width: 42mm;
  padding: 1mm 0;
  font-size: 8pt;
  text-transform: uppercase;
  letter-spacing: 0.3pt;
  color: {_MUTED};
}}

.refs .ref-value {{
  padding: 1mm 0;
}}

/* Items and totals: separated by rules, not an enclosing border */
.items {{
  margin-top: 10mm;
}}

.items th,
.items td {{
  padding: 2mm 2mm 1.5mm 0;
}}

.items thead th {{
  border-top: 1pt solid {_ACCENT};
  border-bottom: 0.5pt solid {_ACCENT};
  color: {_ACCENT};
  text-transform: uppercase;
  font-size: 8pt;
  letter-spacing: 0.3pt;
  padding-top: 2.5mm;
  padding-bottom: 2.5mm;
}}

.items tbody td {{
  border-bottom: 0.4pt solid {_RULE};
}}

.items tr {{
  break-inside: avoid;
}}

.totals {{
  margin-top: 1mm;
  border-top: 0.75pt solid {_ACCENT};
  break-inside: avoid;
}}

.totals th,
.totals td {{
  padding: 1.5mm 2mm 1.5mm 0;
}}

.totals .grand {{
  font-weight: bold;
  color: {_ACCENT};
}}

/* Free-text box: only rendered at all when there's a note (see the template) */
.notes {{
  margin-top: 6mm;
  padding: 2mm 3mm;
  border: 0.75pt solid {_RULE};
  white-space: pre-line;
  break-inside: avoid;
}}

/* Seller details, grouped into three themed columns: registration+bank, domicile+address,
   phone+email — each field is a label/value pair in the same style as .meta/.refs/.amount-due
   above, so the footer reads as part of the same document rather than a separately-styled block.
   Deliberately smaller than the rest of the page (see _FOOTER_* below): this is the block a
   reader consults only when they need one specific fact, not something to read top to bottom. */
.footer {{
  margin-top: 55mm;
  padding-top: 6mm;
  border-top: 0.5pt solid {_RULE};
  font-size: {_FOOTER_SIZE};
  line-height: 1.3;
  break-inside: avoid;
}}

.footer-col {{
  width: 27%;
  padding-right: 6mm;
  vertical-align: top;
}}

.footer-col-wide {{
  width: 38%;
}}

.footer-field {{
  margin-bottom: 1.8mm;
}}

.footer-field:last-child {{
  margin-bottom: 0;
}}

.footer-label {{
  font-size: {_FOOTER_LABEL_SIZE};
  text-transform: uppercase;
  letter-spacing: 0.3pt;
  color: {_MUTED};
}}

.footer a {{
  color: {_ACCENT};
}}
"""


def _write_theme_files() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="time-reporting-invoice-theme-"))
    (directory / TEMPLATE_FILENAME).write_text(_TEMPLATE, encoding="utf-8")
    (directory / CSS_FILENAME).write_text(_CSS, encoding="utf-8")
    return directory


THEME_DIR = _write_theme_files()
