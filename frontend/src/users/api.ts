import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type UserSummary = components["schemas"]["UserSummaryResponse"];

/** Active users matching `search` (name or email substring), for pickers such as adding a
 * project member. Requires manager access (admin or project manager). */
export async function searchUserDirectory(params: {
  search?: string;
  limit?: number;
}): Promise<UserSummary[]> {
  const { data, response } = await api.GET("/api/v1/users/directory", {
    params: { query: { search: params.search, limit: params.limit } },
  });
  if (!data) throw new ApiError(response);
  return data;
}
