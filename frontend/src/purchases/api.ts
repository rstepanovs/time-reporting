import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type PurchaseDocument = components["schemas"]["PurchaseDocumentResponse"];
export type PurchaseStage = PurchaseDocument["stage"];
export type PurchaseKind = NonNullable<PurchaseDocument["kind"]>;
export type PaymentMethod = NonNullable<PurchaseDocument["payment_method"]>;
export type PaymentStatus = NonNullable<PurchaseDocument["payment_status"]>;
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

export async function listPurchaseDocuments(
  params: { stage?: PurchaseStage; kind?: PurchaseKind } = {},
): Promise<PurchaseDocument[]> {
  const { data, response } = await api.GET("/api/v1/purchases/documents", {
    params: { query: { stage: params.stage, kind: params.kind } },
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
