import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type RemovalImpact = components["schemas"]["RemovalImpactResponse"];
export type RemovalOutcome = components["schemas"]["RemovalOutcome"];
export type RemovalCount = components["schemas"]["RemovalCountResponse"];

/** The three record kinds the admin API can archive or permanently delete. */
export type RemovableEntity = "users" | "customers" | "projects";

/** A permanent delete was refused (409): other data still references the record. */
export class RemovalBlockedError extends Error {
  readonly blockers: RemovalCount[];

  constructor(blockers: RemovalCount[]) {
    super("This record is referenced by other data and cannot be deleted");
    this.name = "RemovalBlockedError";
    this.blockers = blockers;
  }
}

/** A business rule was violated, e.g. removing your own account (400). The backend's message. */
export class RemovalRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RemovalRuleError";
  }
}

export class RemovalNotFoundError extends Error {
  constructor() {
    super("Record not found");
    this.name = "RemovalNotFoundError";
  }
}

async function removalAwareError(response: Response): Promise<Error> {
  if (response.status === 404) return new RemovalNotFoundError();
  if (response.status === 400) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new RemovalRuleError(body?.detail ?? "This action is not allowed");
  }
  if (response.status === 409) {
    const body = (await response.clone().json().catch(() => null)) as {
      detail?: { blockers?: RemovalCount[] };
    } | null;
    return new RemovalBlockedError(body?.detail?.blockers ?? []);
  }
  return new ApiError(response);
}

export async function getRemovalImpact(
  entity: RemovableEntity,
  id: string,
): Promise<RemovalImpact> {
  const { data, response } = await (entity === "users"
    ? api.GET("/api/v1/admin/users/{user_id}/removal-impact", {
        params: { path: { user_id: id } },
      })
    : entity === "customers"
      ? api.GET("/api/v1/admin/customers/{customer_id}/removal-impact", {
          params: { path: { customer_id: id } },
        })
      : api.GET("/api/v1/admin/projects/{project_id}/removal-impact", {
          params: { path: { project_id: id } },
        }));
  if (!data) throw await removalAwareError(response);
  return data;
}

export async function removeEntity(
  entity: RemovableEntity,
  id: string,
  options: { permanent: boolean },
): Promise<RemovalOutcome> {
  const { data, response } = await (entity === "users"
    ? api.DELETE("/api/v1/admin/users/{user_id}", {
        params: { path: { user_id: id }, query: { permanent: options.permanent } },
      })
    : entity === "customers"
      ? api.DELETE("/api/v1/admin/customers/{customer_id}", {
          params: { path: { customer_id: id }, query: { permanent: options.permanent } },
        })
      : api.DELETE("/api/v1/admin/projects/{project_id}", {
          params: { path: { project_id: id }, query: { permanent: options.permanent } },
        }));
  if (!data) throw await removalAwareError(response);
  return data.outcome;
}
