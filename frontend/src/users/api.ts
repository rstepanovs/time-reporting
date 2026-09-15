import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type UserSummary = components["schemas"]["UserSummaryResponse"];
export type User = components["schemas"]["UserResponse"];
export type UserPage = components["schemas"]["UserPageResponse"];
export type UserRole = components["schemas"]["UserRole"];

/** A user with this email already exists (409). */
export class UserEmailConflictError extends Error {
  constructor() {
    super("A user with this email already exists");
    this.name = "UserEmailConflictError";
  }
}

/** A business rule was violated, e.g. an admin editing their own role (400). The backend's
 * message. */
export class UserRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UserRuleError";
  }
}

export class UserNotFoundError extends Error {
  constructor() {
    super("User not found");
    this.name = "UserNotFoundError";
  }
}

async function userAwareError(response: Response): Promise<Error> {
  if (response.status === 409) return new UserEmailConflictError();
  if (response.status === 404) return new UserNotFoundError();
  if (response.status === 400) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new UserRuleError(body?.detail ?? "This action is not allowed");
  }
  return new ApiError(response);
}

/** Active users matching `search` (name or email substring), for pickers such as adding a
 * project member or a project's manager (`roles`, any-of). Requires manager access. */
export async function searchUserDirectory(params: {
  search?: string;
  limit?: number;
  roles?: UserRole[];
}): Promise<UserSummary[]> {
  const { data, response } = await api.GET("/api/v1/users/directory", {
    params: { query: { search: params.search, limit: params.limit, role: params.roles } },
  });
  if (!data) throw new ApiError(response);
  return data;
}

/** Admin-only: the full user list (active and inactive by default), for the administration page. */
export async function listUsers(params: {
  search?: string;
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
}): Promise<UserPage> {
  const { data, response } = await api.GET("/api/v1/users", {
    params: {
      query: {
        search: params.search,
        include_inactive: params.includeInactive,
        limit: params.limit,
        offset: params.offset,
      },
    },
  });
  if (!data) throw new ApiError(response);
  return data;
}

export async function createUser(body: {
  name: string;
  email: string;
  roles: UserRole[];
  password: string;
}): Promise<User> {
  const { data, response } = await api.POST("/api/v1/users", { body });
  if (!data) throw await userAwareError(response);
  return data;
}

export async function updateUser(
  userId: string,
  body: { name?: string; email?: string; roles?: UserRole[]; is_active?: boolean },
): Promise<User> {
  const { data, response } = await api.PATCH("/api/v1/users/{user_id}", {
    params: { path: { user_id: userId } },
    body,
  });
  if (!data) throw await userAwareError(response);
  return data;
}

export async function resetUserPassword(userId: string, newPassword: string): Promise<void> {
  const { response } = await api.PUT("/api/v1/users/{user_id}/password", {
    params: { path: { user_id: userId } },
    body: { new_password: newPassword },
  });
  if (!response.ok) throw await userAwareError(response);
}
