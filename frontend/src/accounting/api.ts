import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type AccountantPackageStatus = components["schemas"]["AccountantPackageStatusResponse"];
export type AccountantPackageTotal = components["schemas"]["AccountantPackageTotalResponse"];

/** What `BuildAccountantPackage` would produce right now for `year`/`month`, plus the three
 * warnings shown as `Alert`s on `/accounting`. */
export async function getAccountantPackageStatus(
  year: number,
  month: number,
): Promise<AccountantPackageStatus> {
  const { data, response } = await api.GET("/api/v1/accounting/packages/{year}/{month}", {
    params: { path: { year, month } },
  });
  if (!data) throw new ApiError(response);
  return data;
}

/** Relative URL for the month's package ZIP; used directly as an `<a href download>`, never
 * fetched through `api` — following `attachmentDownloadUrl`/`invoicePdfUrl`. */
export function accountantPackageDownloadUrl(year: number, month: number): string {
  return `/api/v1/accounting/packages/${year}/${month}.zip`;
}
