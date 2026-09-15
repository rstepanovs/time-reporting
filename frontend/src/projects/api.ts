import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type Project = components["schemas"]["ProjectResponse"];
export type ProjectManager = components["schemas"]["ProjectManagerResponse"];
export type ProjectPage = components["schemas"]["ProjectPageResponse"];
export type ProjectMember = components["schemas"]["ProjectMemberResponse"];
export type BillingItem = components["schemas"]["ProjectBillingItemResponse"];
export type BillingUnit = components["schemas"]["BillingUnit"];
export type BillingItemPreset = components["schemas"]["BillingItemPreset"];

/** A project name is already taken for that customer (409). */
export class ProjectConflictError extends Error {
  constructor() {
    super("A project with this name already exists for this customer");
    this.name = "ProjectConflictError";
  }
}

/** A business rule was violated, e.g. the customer is archived (400). The backend's message. */
export class ProjectRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProjectRuleError";
  }
}

/** The project (or, for member operations, the membership) was not found (404). */
export class ProjectNotFoundError extends Error {
  constructor() {
    super("Project not found");
    this.name = "ProjectNotFoundError";
  }
}

/** A billing item with this name already exists for the project (409). */
export class BillingItemConflictError extends Error {
  constructor() {
    super("A billing item with this name already exists for this project");
    this.name = "BillingItemConflictError";
  }
}

/** The billing item is referenced by other data and cannot be permanently deleted (409). */
export class BillingItemInUseError extends Error {
  constructor() {
    super("This billing item is referenced by other data and cannot be deleted");
    this.name = "BillingItemInUseError";
  }
}

async function ruleAwareError(response: Response): Promise<Error> {
  if (response.status === 409) return new ProjectConflictError();
  if (response.status === 404) return new ProjectNotFoundError();
  if (response.status === 400) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new ProjectRuleError(body?.detail ?? "This action is not allowed");
  }
  return new ApiError(response);
}

// A billing item's 409 means two different things depending on the route (a name conflict on
// create/update, "still in use" on delete), so each gets its own mapping instead of reusing
// ruleAwareError's single 409 case.
async function billingItemWriteError(response: Response): Promise<Error> {
  if (response.status === 409) return new BillingItemConflictError();
  if (response.status === 404) return new ProjectNotFoundError();
  if (response.status === 400) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new ProjectRuleError(body?.detail ?? "This action is not allowed");
  }
  return new ApiError(response);
}

async function billingItemDeleteError(response: Response): Promise<Error> {
  if (response.status === 409) return new BillingItemInUseError();
  if (response.status === 404) return new ProjectNotFoundError();
  return new ApiError(response);
}

export async function listProjects(params: {
  limit?: number;
  offset?: number;
  includeInactive?: boolean;
  customerId?: string;
  memberId?: string;
  managerId?: string;
  search?: string;
}): Promise<ProjectPage> {
  const { data, response } = await api.GET("/api/v1/projects", {
    params: {
      query: {
        limit: params.limit,
        offset: params.offset,
        include_inactive: params.includeInactive,
        customer_id: params.customerId,
        member_id: params.memberId,
        manager_id: params.managerId,
        search: params.search,
      },
    },
  });
  if (!data) throw new ApiError(response);
  return data;
}

export async function getProject(projectId: string): Promise<Project> {
  const { data, response } = await api.GET("/api/v1/projects/{project_id}", {
    params: { path: { project_id: projectId } },
  });
  if (!data) throw await ruleAwareError(response);
  return data;
}

export async function createProject(body: {
  customerId: string;
  name: string;
  description?: string | null;
  normalWorkingHours: number | string;
  managerId?: string | null;
}): Promise<Project> {
  const { data, response } = await api.POST("/api/v1/projects", {
    body: {
      customer_id: body.customerId,
      name: body.name,
      description: body.description,
      normal_working_hours: body.normalWorkingHours,
      manager_id: body.managerId,
    },
  });
  if (!data) throw await ruleAwareError(response);
  return data;
}

export async function updateProject(
  projectId: string,
  body: {
    name?: string;
    description?: string | null;
    is_active?: boolean;
    normal_working_hours?: number | string;
    manager_id?: string | null;
  },
): Promise<Project> {
  const { data, response } = await api.PATCH("/api/v1/projects/{project_id}", {
    params: { path: { project_id: projectId } },
    body,
  });
  if (!data) throw await ruleAwareError(response);
  return data;
}

export async function listProjectMembers(projectId: string): Promise<ProjectMember[]> {
  const { data, response } = await api.GET("/api/v1/projects/{project_id}/members", {
    params: { path: { project_id: projectId } },
  });
  if (!data) throw await ruleAwareError(response);
  return data;
}

export async function addProjectMember(
  projectId: string,
  userId: string,
): Promise<ProjectMember> {
  const { data, response } = await api.POST("/api/v1/projects/{project_id}/members", {
    params: { path: { project_id: projectId } },
    body: { user_id: userId },
  });
  if (!data) throw await ruleAwareError(response);
  return data;
}

export async function removeProjectMember(projectId: string, userId: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/projects/{project_id}/members/{user_id}", {
    params: { path: { project_id: projectId, user_id: userId } },
  });
  if (!response.ok) throw await ruleAwareError(response);
}

export async function listProjectBillingItems(
  projectId: string,
  includeInactive = false,
): Promise<BillingItem[]> {
  const { data, response } = await api.GET("/api/v1/projects/{project_id}/billing-items", {
    params: { path: { project_id: projectId }, query: { include_inactive: includeInactive } },
  });
  if (!data) throw await ruleAwareError(response);
  return data;
}

export async function addProjectBillingItem(
  projectId: string,
  body: {
    name: string;
    unit: BillingUnit;
    description?: string | null;
    unit_rate?: number | string | null;
    markup_percent?: number | string | null;
  },
): Promise<BillingItem> {
  const { data, response } = await api.POST("/api/v1/projects/{project_id}/billing-items", {
    params: { path: { project_id: projectId } },
    body,
  });
  if (!data) throw await billingItemWriteError(response);
  return data;
}

export async function updateProjectBillingItem(
  projectId: string,
  itemId: string,
  body: {
    name?: string;
    description?: string | null;
    unit_rate?: number | string | null;
    markup_percent?: number | string | null;
    is_active?: boolean;
  },
): Promise<BillingItem> {
  const { data, response } = await api.PATCH(
    "/api/v1/projects/{project_id}/billing-items/{item_id}",
    { params: { path: { project_id: projectId, item_id: itemId } }, body },
  );
  if (!data) throw await billingItemWriteError(response);
  return data;
}

export async function deleteProjectBillingItem(projectId: string, itemId: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/projects/{project_id}/billing-items/{item_id}", {
    params: { path: { project_id: projectId, item_id: itemId } },
  });
  if (!response.ok) throw await billingItemDeleteError(response);
}
