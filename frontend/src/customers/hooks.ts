import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCustomer,
  type CustomerCreateBody,
  type CustomerUpdateBody,
  getCustomer,
  listCustomers,
  updateCustomer,
} from "@/customers/api";

export const customerKeys = {
  all: ["customers"] as const,
  list: (params: Parameters<typeof listCustomers>[0]) =>
    [...customerKeys.all, "list", params] as const,
  detail: (id: string) => [...customerKeys.all, "detail", id] as const,
};

export function useCustomers(
  params: { includeInactive?: boolean; limit?: number; offset?: number; search?: string } = {},
) {
  return useQuery({
    queryKey: customerKeys.list(params),
    queryFn: () => listCustomers(params),
  });
}

export function useCustomer(customerId: string) {
  return useQuery({
    queryKey: customerKeys.detail(customerId),
    queryFn: () => getCustomer(customerId),
  });
}

export function useCreateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CustomerCreateBody) => createCustomer(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: customerKeys.all }),
  });
}

export function useUpdateCustomer(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CustomerUpdateBody) => updateCustomer(customerId, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: customerKeys.all });
      // Projects display their customer's name and archived status.
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
