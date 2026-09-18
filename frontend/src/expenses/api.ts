import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type ExpenseCustomer = components["schemas"]["ExpenseCustomerResponse"];
export type ExpenseProject = components["schemas"]["ExpenseProjectResponse"];
export type ExpenseBillingItem = components["schemas"]["ExpenseBillingItemResponse"];
export type ExpenseOption = components["schemas"]["ExpenseOptionResponse"];
export type ExpenseLine = components["schemas"]["ExpenseLineResponse"];
export type ExpenseLineChange = components["schemas"]["ExpenseLineChangeRequest"];
export type ExpenseAttachment = components["schemas"]["ExpenseAttachmentResponse"];
export type ExpenseReport = components["schemas"]["ExpenseReportResponse"];
export type ExpenseReportStatus = components["schemas"]["ExpenseReportResponse"]["status"];
export type ExpenseReportSummary = components["schemas"]["ExpenseReportSummaryResponse"];
export type ExpenseScope = "mine" | "all";

/** A rule was violated while reading/saving/reviewing a report (400/403/404). The backend's
 * message, or a generic one for a 403 that carries no body. */
export class ExpenseRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExpenseRuleError";
  }
}

/** The report's status (or lock) doesn't allow this action (409) — e.g. saving a submitted
 * report, or submitting/approving/returning from the wrong status, or a locked report. The
 * backend's message. */
export class ExpenseConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExpenseConflictError";
  }
}

/** An uploaded attachment exceeded `attachment_max_bytes` (413). */
export class AttachmentTooLargeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AttachmentTooLargeError";
  }
}

/** An uploaded attachment's content type isn't in the allowed set (415). */
export class AttachmentTypeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AttachmentTypeError";
  }
}

async function expenseAwareError(response: Response): Promise<Error> {
  if (response.status === 409) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new ExpenseConflictError(body?.detail ?? "This report's status has changed");
  }
  if (response.status === 400 || response.status === 404) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new ExpenseRuleError(body?.detail ?? "This action is not allowed");
  }
  if (response.status === 403) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new ExpenseRuleError(body?.detail ?? "You cannot view another user's expense reports");
  }
  return new ApiError(response);
}

async function attachmentAwareError(response: Response): Promise<Error> {
  if (response.status === 413) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new AttachmentTooLargeError(body?.detail ?? "This file is too large");
  }
  if (response.status === 415) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new AttachmentTypeError(body?.detail ?? "This file type is not allowed");
  }
  return expenseAwareError(response);
}

/** The caller's own project/billing-item picker, for starting a new report. */
export async function listExpenseOptions(): Promise<ExpenseOption[]> {
  const { data, response } = await api.GET("/api/v1/expenses/options");
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** One month's reports for `userId` (default: the caller's own); another user needs manager. */
export async function listMyExpenseReports(params: {
  year: number;
  month: number;
  userId?: string;
}): Promise<ExpenseReportSummary[]> {
  const { data, response } = await api.GET("/api/v1/expenses/reports", {
    params: { query: { year: params.year, month: params.month, user_id: params.userId } },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** Start a new draft report for one project and calendar month. */
export async function createExpenseReport(params: {
  projectId: string;
  year: number;
  month: number;
}): Promise<ExpenseReport> {
  const { data, response } = await api.POST("/api/v1/expenses/reports", {
    body: { project_id: params.projectId, year: params.year, month: params.month },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

export async function getExpenseReport(reportId: string): Promise<ExpenseReport> {
  const { data, response } = await api.GET("/api/v1/expenses/reports/{report_id}", {
    params: { path: { report_id: reportId } },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** Replace the changed lines and delete the removed ones in one batch. */
export async function saveExpenseReportLines(
  reportId: string,
  lines: ExpenseLineChange[],
  deleteLineIds: string[] = [],
): Promise<ExpenseReport> {
  const { data, response } = await api.PUT("/api/v1/expenses/reports/{report_id}/lines", {
    params: { path: { report_id: reportId } },
    body: { lines, delete_line_ids: deleteLineIds },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** Delete a draft report entirely. */
export async function deleteExpenseReport(reportId: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/expenses/reports/{report_id}", {
    params: { path: { report_id: reportId } },
  });
  if (!response.ok) throw await expenseAwareError(response);
}

/** Submit the caller's own report for review. */
export async function submitExpenseReport(reportId: string): Promise<ExpenseReport> {
  const { data, response } = await api.POST("/api/v1/expenses/reports/{report_id}/submit", {
    params: { path: { report_id: reportId } },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** Approve a submitted report (manager only, not the report's own owner). */
export async function approveExpenseReport(reportId: string): Promise<ExpenseReport> {
  const { data, response } = await api.POST("/api/v1/expenses/reports/{report_id}/approve", {
    params: { path: { report_id: reportId } },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** Return a submitted/approved report for corrections, with an explanatory comment. */
export async function returnExpenseReport(params: {
  reportId: string;
  comment: string;
}): Promise<ExpenseReport> {
  const { data, response } = await api.POST("/api/v1/expenses/reports/{report_id}/return", {
    params: { path: { report_id: params.reportId } },
    body: { comment: params.comment },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** Reports awaiting review, a manager's Expenses tab of `/approvals`. `scope: "mine"` narrows to
 * projects the caller manages; `"all"` (the default) matches every project. */
export async function listSubmittedExpenseReports(
  params: { scope?: ExpenseScope } = {},
): Promise<ExpenseReportSummary[]> {
  const { data, response } = await api.GET("/api/v1/expenses/submissions", {
    params: { query: { scope: params.scope } },
  });
  if (!data) throw await expenseAwareError(response);
  return data;
}

/** `openapi-fetch` skips the JSON content type and passes the `FormData` this builds straight
 * through — the typed `file` field is a string only because OpenAPI has no distinct "binary"
 * type, so the actual `File` is cast rather than converted. */
function formDataBodySerializer(body: Record<string, unknown>): FormData {
  const formData = new FormData();
  for (const [key, value] of Object.entries(body)) {
    if (value !== undefined && value !== null) formData.append(key, value as string | Blob);
  }
  return formData;
}

/** Upload a receipt/invoice scan to a report the caller owns and can still edit. */
export async function addExpenseAttachment(params: {
  reportId: string;
  file: File;
  fileName?: string;
}): Promise<ExpenseAttachment> {
  const { data, response } = await api.POST("/api/v1/expenses/reports/{report_id}/attachments", {
    params: { path: { report_id: params.reportId } },
    body: { file: params.file as unknown as string, file_name: params.fileName ?? null },
    bodySerializer: formDataBodySerializer,
  });
  if (!data) throw await attachmentAwareError(response);
  return data;
}

/** Relative download URL for an attachment; used directly as an `<a href download>`, not fetched
 * via `api` — following `backupDownloadUrl`. */
export function attachmentDownloadUrl(attachmentId: string): string {
  return `/api/v1/expenses/attachments/${encodeURIComponent(attachmentId)}`;
}

export async function deleteExpenseAttachment(attachmentId: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/expenses/attachments/{attachment_id}", {
    params: { path: { attachment_id: attachmentId } },
  });
  if (!response.ok) throw await expenseAwareError(response);
}
