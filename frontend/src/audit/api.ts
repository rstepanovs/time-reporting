import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type AuditAction = components["schemas"]["AuditAction"];
export type AuditEvent = components["schemas"]["AuditEventResponse"];
export type AuditEventPage = components["schemas"]["AuditEventPageResponse"];

/** Admin only: the administrative audit log, newest first, filterable by action/entity
 * type/actor/date range and paginated. */
export async function listAuditEvents(
  params: {
    action?: AuditAction;
    entityType?: string;
    actorId?: string;
    occurredFrom?: string;
    occurredTo?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AuditEventPage> {
  const { data, response } = await api.GET("/api/v1/admin/audit-events", {
    params: {
      query: {
        action: params.action,
        entity_type: params.entityType,
        actor_id: params.actorId,
        occurred_from: params.occurredFrom,
        occurred_to: params.occurredTo,
        limit: params.limit,
        offset: params.offset,
      },
    },
  });
  if (!data) throw new ApiError(response);
  return data;
}
