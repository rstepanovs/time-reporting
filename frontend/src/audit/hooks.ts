import { useQuery } from "@tanstack/react-query";

import { listAuditEvents } from "@/audit/api";

export const auditKeys = {
  all: ["audit"] as const,
  events: (params: Parameters<typeof listAuditEvents>[0]) =>
    [...auditKeys.all, "events", params] as const,
};

/** Admin only: the `/admin/audit` page's paginated, filtered event list. */
export function useAuditEvents(params: Parameters<typeof listAuditEvents>[0] = {}) {
  return useQuery({
    queryKey: auditKeys.events(params),
    queryFn: () => listAuditEvents(params),
  });
}
