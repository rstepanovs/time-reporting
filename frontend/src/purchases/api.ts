import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type PurchaseDocument = components["schemas"]["PurchaseDocumentResponse"];
export type PurchaseStage = PurchaseDocument["stage"];
export type PurchaseKind = NonNullable<PurchaseDocument["kind"]>;
export type PaymentMethod = NonNullable<PurchaseDocument["payment_method"]>;
export type PaymentStatus = NonNullable<PurchaseDocument["payment_status"]>;
export type PurchaseDocumentPage = components["schemas"]["PurchaseDocumentPageResponse"];
export type CardInvoice = components["schemas"]["CardInvoiceResponse"];
export type RebillSuggestion = components["schemas"]["RebillSuggestionResponse"];
export type PurchaseSort = components["schemas"]["PurchaseSort"];
export type PurchaseDetails = components["schemas"]["PurchaseDetailsRequest"];
export type PurchasesSummary = components["schemas"]["PurchasesSummaryResponse"];
export type ExchangeRate = components["schemas"]["ExchangeRateResponse"];

/** The fields rule of the document's kind was broken, or the document/currency is unknown
 * (400/404). The backend's message. */
export class PurchaseRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PurchaseRuleError";
  }
}

/** The document's state doesn't allow this (409) — already discarded, rebilled, paid... */
export class PurchaseConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PurchaseConflictError";
  }
}

/** An uploaded file exceeded the size limit (413). */
export class PurchaseFileTooLargeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PurchaseFileTooLargeError";
  }
}

/** An uploaded file's type isn't allowed (415). */
export class PurchaseFileTypeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PurchaseFileTypeError";
  }
}

async function detailOf(response: Response, fallback: string): Promise<string> {
  const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
  return typeof body?.detail === "string" ? body.detail : fallback;
}

async function purchaseAwareError(response: Response): Promise<Error> {
  switch (response.status) {
    case 400:
    case 404:
      return new PurchaseRuleError(await detailOf(response, "This action is not allowed"));
    case 409:
      return new PurchaseConflictError(
        await detailOf(response, "The document's state has changed"),
      );
    case 413:
      return new PurchaseFileTooLargeError(await detailOf(response, "This file is too large"));
    case 415:
      return new PurchaseFileTypeError(await detailOf(response, "This file type is not allowed"));
    default:
      return new ApiError(response);
  }
}

export type PurchaseListParams = {
  stage?: PurchaseStage;
  kind?: PurchaseKind;
  paymentStatus?: PaymentStatus;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  sort?: PurchaseSort;
  limit?: number;
  offset?: number;
};

/** One page of documents; every filter is optional (see the backend's `ListPurchaseDocuments`). */
export async function listPurchaseDocuments(
  params: PurchaseListParams = {},
): Promise<PurchaseDocumentPage> {
  const { data, response } = await api.GET("/api/v1/purchases/documents", {
    params: {
      query: {
        stage: params.stage,
        kind: params.kind,
        payment_status: params.paymentStatus,
        search: params.search || undefined,
        date_from: params.dateFrom || undefined,
        date_to: params.dateTo || undefined,
        sort: params.sort,
        limit: params.limit,
        offset: params.offset,
      },
    },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

export async function getPurchaseDocument(documentId: string): Promise<PurchaseDocument> {
  const { data, response } = await api.GET("/api/v1/purchases/documents/{document_id}", {
    params: { path: { document_id: documentId } },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

export async function getPurchasesSummary(): Promise<PurchasesSummary> {
  const { data, response } = await api.GET("/api/v1/purchases/summary");
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** `openapi-fetch` passes the `FormData` this builds straight through and skips the JSON content
 * type; repeated `files` entries become one multipart field per file. The generated type says
 * `string[]` only because OpenAPI has no distinct binary type. */
function filesBodySerializer(body: { files: unknown }): FormData {
  const formData = new FormData();
  for (const file of body.files as File[]) formData.append("files", file);
  return formData;
}

/** Upload one or more files into the inbox; a bad file rejects the whole batch. */
export async function uploadPurchaseDocuments(files: File[]): Promise<PurchaseDocument[]> {
  const { data, response } = await api.POST("/api/v1/purchases/documents", {
    body: { files: files as unknown as string[] },
    bodySerializer: filesBodySerializer,
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

export async function discardPurchaseDocument(documentId: string): Promise<PurchaseDocument> {
  const { data, response } = await api.POST("/api/v1/purchases/documents/{document_id}/discard", {
    params: { path: { document_id: documentId } },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Classify an inbox document. */
export async function registerPurchaseDocument(params: {
  documentId: string;
  details: PurchaseDetails;
}): Promise<PurchaseDocument> {
  const { data, response } = await api.POST("/api/v1/purchases/documents/{document_id}/register", {
    params: { path: { document_id: params.documentId } },
    body: params.details,
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Replace a registered document's fields. A manual base-currency amount survives unless the
 * amount/currency changes or `recomputeConversion` is set. */
export async function updatePurchaseDocument(params: {
  documentId: string;
  details: PurchaseDetails;
  recomputeConversion?: boolean;
}): Promise<PurchaseDocument> {
  const { data, response } = await api.PUT("/api/v1/purchases/documents/{document_id}", {
    params: { path: { document_id: params.documentId } },
    body: { ...params.details, recompute_conversion: params.recomputeConversion ?? false },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Pay an unpaid invoice/card invoice. `amountBase` is what the bank actually debited in the base
 * currency; omit it to convert at the rate of `paidOn`. */
export async function markPurchasePaid(params: {
  documentId: string;
  paidOn: string;
  paymentMethod: PaymentMethod;
  amountBase?: string | null;
}): Promise<PurchaseDocument> {
  const { data, response } = await api.POST("/api/v1/purchases/documents/{document_id}/paid", {
    params: { path: { document_id: params.documentId } },
    body: {
      paid_on: params.paidOn,
      payment_method: params.paymentMethod,
      amount_base: params.amountBase || null,
    },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

export async function markPurchaseUnpaid(documentId: string): Promise<PurchaseDocument> {
  const { data, response } = await api.POST("/api/v1/purchases/documents/{document_id}/unpaid", {
    params: { path: { document_id: documentId } },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Undo a registration: the document goes back to the inbox, unclassified. */
export async function returnPurchaseToInbox(documentId: string): Promise<PurchaseDocument> {
  const { data, response } = await api.POST(
    "/api/v1/purchases/documents/{document_id}/return-to-inbox",
    { params: { path: { document_id: documentId } } },
  );
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** A card invoice with its linked receipts, their base-currency sum and the difference from the
 * card invoice's own total (fees, interest, purchases without a receipt). */
export async function getCardInvoice(documentId: string): Promise<CardInvoice> {
  const { data, response } = await api.GET("/api/v1/purchases/documents/{document_id}/card-invoice", {
    params: { path: { document_id: documentId } },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Card-paid receipts not yet linked to a card invoice, oldest first, optionally date-bounded. */
export async function listUnlinkedCardReceipts(
  params: { dateFrom?: string; dateTo?: string } = {},
): Promise<PurchaseDocument[]> {
  const { data, response } = await api.GET("/api/v1/purchases/card-receipts/unlinked", {
    params: {
      query: { date_from: params.dateFrom || undefined, date_to: params.dateTo || undefined },
    },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Link receipts to a card invoice, each with its base-currency amount from the card invoice's
 * lines; all or nothing. */
export async function linkCardReceipts(params: {
  cardInvoiceId: string;
  links: { receiptId: string; amountBase: string }[];
}): Promise<CardInvoice> {
  const { data, response } = await api.POST(
    "/api/v1/purchases/documents/{document_id}/card-receipts",
    {
      params: { path: { document_id: params.cardInvoiceId } },
      body: {
        links: params.links.map((link) => ({
          receipt_id: link.receiptId,
          amount_base: link.amountBase,
        })),
      },
    },
  );
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Retype a linked receipt's base-currency amount (the receipt's id, not the card invoice's). */
export async function updateCardReceiptAmount(params: {
  receiptId: string;
  amountBase: string;
}): Promise<PurchaseDocument> {
  const { data, response } = await api.PUT("/api/v1/purchases/documents/{document_id}/card-amount", {
    params: { path: { document_id: params.receiptId } },
    body: { amount_base: params.amountBase },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

export async function unlinkCardReceipt(receiptId: string): Promise<PurchaseDocument> {
  const { data, response } = await api.POST("/api/v1/purchases/documents/{document_id}/unlink-card", {
    params: { path: { document_id: receiptId } },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** Defaults for rebilling to `projectId`: the amount in the customer's currency, the date and a
 * description. */
export async function getRebillSuggestion(params: {
  documentId: string;
  projectId: string;
}): Promise<RebillSuggestion> {
  const { data, response } = await api.GET(
    "/api/v1/purchases/documents/{document_id}/rebill-suggestion",
    {
      params: {
        path: { document_id: params.documentId },
        query: { project_id: params.projectId },
      },
    },
  );
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** File a receipt/invoice to a project's expense report (the caller's own, for the month). */
export async function rebillPurchase(params: {
  documentId: string;
  projectId: string;
  year: number;
  month: number;
  billingItemId: string;
  description: string;
  amount?: string | null;
  expenseDate?: string | null;
}): Promise<PurchaseDocument> {
  const { data, response } = await api.POST("/api/v1/purchases/documents/{document_id}/rebill", {
    params: { path: { document_id: params.documentId } },
    body: {
      project_id: params.projectId,
      year: params.year,
      month: params.month,
      billing_item_id: params.billingItemId,
      description: params.description,
      amount: params.amount || null,
      expense_date: params.expenseDate || null,
    },
  });
  if (!data) throw await purchaseAwareError(response);
  return data;
}

/** SEK per one unit of `currency` on `on` (or the latest published rate before it). */
export async function getExchangeRate(params: { currency: string; on: string }): Promise<ExchangeRate> {
  const { data, response } = await api.GET("/api/v1/currency/rates/{currency}", {
    params: { path: { currency: params.currency }, query: { on: params.on } },
  });
  if (!data) throw new PurchaseRuleError(await detailOf(response, "No exchange rate available"));
  return data;
}

/** Relative URL of a document's file, for an `<iframe>`/`<img>`/`<a href>` — never fetched via
 * `api`, following `attachmentDownloadUrl`. */
export function purchaseFileUrl(documentId: string): string {
  return `/api/v1/purchases/documents/${encodeURIComponent(documentId)}/file`;
}
