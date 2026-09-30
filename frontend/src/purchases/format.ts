import type { PaymentMethod, PurchaseDocument, PurchaseKind } from "@/purchases/api";

export const KIND_LABEL: Record<PurchaseKind, string> = {
  receipt: "Receipt",
  invoice: "Invoice",
  card_invoice: "Card invoice",
  other: "Other",
};

export const METHOD_LABEL: Record<PaymentMethod, string> = {
  card: "Card",
  bank_transfer: "Bank transfer",
  direct_debit: "Direct debit",
  cash: "Cash",
  private: "Paid privately",
};

function money(value: string): string {
  return Number(value).toLocaleString("sv-SE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** The amount as printed on the document, e.g. "100,00 EUR"; empty when it has none. */
export function formatAmount(document: PurchaseDocument): string {
  if (document.amount === null) return "";
  return `${money(document.amount)} ${document.currency ?? ""}`.trim();
}

/** The base-currency amount; `~` marks one that is still an estimate (not final), "—" one that is
 * missing (a card receipt awaiting its card invoice, or a currency with no published rate). */
export function formatBaseAmount(document: PurchaseDocument, baseCurrency: string): string {
  if (document.amount === null) return "";
  if (document.amount_base === null) return "—";
  const estimate = document.amount_base_final ? "" : "~";
  return `${estimate}${money(document.amount_base)} ${baseCurrency}`;
}

/** "Paid 2026-09-25", "Due 2026-10-24" or "" — the document's payment state in a few words. */
export function paymentStatusText(document: PurchaseDocument): string {
  if (document.payment_status === "paid" && document.paid_on) return `Paid ${document.paid_on}`;
  if (document.payment_status === "unpaid" && document.due_date) return `Due ${document.due_date}`;
  return "";
}
