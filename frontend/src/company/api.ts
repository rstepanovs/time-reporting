import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type CompanySettings = components["schemas"]["CompanySettingsResponse"];
export type CompanyAddress = components["schemas"]["CompanyAddressRequest"];
export type CompanySettingsUpdateBody = components["schemas"]["CompanySettingsUpdateRequest"];
export type InvoiceLocale = components["schemas"]["InvoiceLocale"];

export const INVOICE_LOCALE_OPTIONS: { value: InvoiceLocale; label: string }[] = [
  { value: "sv", label: "Swedish" },
  { value: "en", label: "English" },
];

/** The logo is over the 512 KB limit (413). */
export class CompanyLogoTooLargeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CompanyLogoTooLargeError";
  }
}

/** The uploaded file's type isn't one of SVG/PNG/JPEG (415). */
export class CompanyLogoTypeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CompanyLogoTypeError";
  }
}

async function detailMessage(response: Response, fallback: string): Promise<string> {
  const body: unknown = await response.json().catch(() => null);
  if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
    return body.detail;
  }
  return fallback;
}

export async function getCompanySettings(): Promise<CompanySettings> {
  const { data, response } = await api.GET("/api/v1/company");
  if (!data) throw new ApiError(response);
  return data;
}

export async function updateCompanySettings(
  body: CompanySettingsUpdateBody,
): Promise<CompanySettings> {
  const { data, response } = await api.PUT("/api/v1/company", { body });
  if (!data) throw new ApiError(response);
  return data;
}

/** Relative URL for the current logo; used directly as an `<img src>`, not fetched via `api`. */
export function companyLogoUrl(): string {
  return "/api/v1/company/logo";
}

function formDataBodySerializer(body: Record<string, unknown>): FormData {
  const formData = new FormData();
  for (const [key, value] of Object.entries(body)) {
    if (value !== undefined && value !== null) formData.append(key, value as string | Blob);
  }
  return formData;
}

export async function setCompanyLogo(file: File): Promise<CompanySettings> {
  const { data, response } = await api.PUT("/api/v1/company/logo", {
    body: { file: file as unknown as string },
    bodySerializer: formDataBodySerializer,
  });
  if (!data) {
    if (response.status === 413) {
      throw new CompanyLogoTooLargeError(
        await detailMessage(response, "Logo is over the size limit"),
      );
    }
    if (response.status === 415) {
      throw new CompanyLogoTypeError(await detailMessage(response, "Logo type is not allowed"));
    }
    throw new ApiError(response);
  }
  return data;
}

export async function clearCompanyLogo(): Promise<CompanySettings> {
  const { data, response } = await api.DELETE("/api/v1/company/logo");
  if (!data) throw new ApiError(response);
  return data;
}
