import { useQuery } from "@tanstack/react-query";

import { listCustomers } from "@/customers/api";

export function useCustomers(params: { includeInactive?: boolean; limit?: number } = {}) {
  return useQuery({
    queryKey: ["customers", "list", params],
    queryFn: () => listCustomers(params),
  });
}
