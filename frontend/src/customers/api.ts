import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type Customer = components["schemas"]["CustomerResponse"];
export type CustomerPage = components["schemas"]["CustomerPageResponse"];

/** Active customers by default; pass `includeInactive` to also list archived ones. */
export async function listCustomers(params: {
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
}): Promise<CustomerPage> {
  const { data, response } = await api.GET("/api/v1/customers", {
    params: {
      query: {
        include_inactive: params.includeInactive,
        limit: params.limit,
        offset: params.offset,
      },
    },
  });
  if (!data) throw new ApiError(response);
  return data;
}
