import { useQuery } from "@tanstack/react-query";

import { getAccountantPackageStatus } from "@/accounting/api";

export const accountingKeys = {
  all: ["accounting"] as const,
  status: (year: number, month: number) =>
    [...accountingKeys.all, "status", year, month] as const,
};

/** The `/accounting` page's data for one month; the ZIP itself is never fetched through the query
 * cache, only linked (`accountantPackageDownloadUrl`). */
export function useAccountantPackageStatus(year: number, month: number) {
  return useQuery({
    queryKey: accountingKeys.status(year, month),
    queryFn: () => getAccountantPackageStatus(year, month),
  });
}
