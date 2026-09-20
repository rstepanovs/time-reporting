import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createInvoiceDraft,
  deleteInvoiceDraft,
  getInvoice,
  issueInvoice,
  listInvoiceablePeriods,
  listInvoices,
  markInvoicePaid,
  updateInvoiceDraft,
  voidInvoice,
} from "@/invoices/api";

export const invoiceKeys = {
  all: ["invoices"] as const,
  invoiceablePeriods: () => [...invoiceKeys.all, "invoiceable-periods"] as const,
  // A shared prefix over every list variant, so a mutation can invalidate "every list" without
  // also invalidating `detail(invoiceId)` — that entry is instead kept in sync directly via
  // `setQueryData`, and invalidating it too would trigger a refetch that could momentarily
  // clobber it with a stale response.
  lists: () => [...invoiceKeys.all, "list"] as const,
  list: (params: Parameters<typeof listInvoices>[0]) => [...invoiceKeys.lists(), params] as const,
  detail: (invoiceId: string) => [...invoiceKeys.all, "detail", invoiceId] as const,
};

/** Every sent, uninvoiced, non-internal billing period, grouped by customer — the "To invoice"
 * tab of `/invoices`. */
export function useInvoiceablePeriods() {
  return useQuery({
    queryKey: invoiceKeys.invoiceablePeriods(),
    queryFn: listInvoiceablePeriods,
  });
}

export function useInvoices(params: Parameters<typeof listInvoices>[0]) {
  return useQuery({
    queryKey: invoiceKeys.list(params),
    queryFn: () => listInvoices(params),
  });
}

export function useInvoice(invoiceId: string) {
  return useQuery({
    queryKey: invoiceKeys.detail(invoiceId),
    queryFn: () => getInvoice(invoiceId),
  });
}

/** Build a draft; the caller navigates to it on success. Marks the periods it covers invoiced, so
 * both the "To invoice" tab and the invoice list need refreshing. */
export function useCreateInvoiceDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createInvoiceDraft,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.invoiceablePeriods() });
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
    },
  });
}

export function useUpdateInvoiceDraft(invoiceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof updateInvoiceDraft>[1]) =>
      updateInvoiceDraft(invoiceId, body),
    onSuccess: (invoice) => {
      queryClient.setQueryData(invoiceKeys.detail(invoiceId), invoice);
    },
  });
}

/** Delete a draft entirely; frees every billing period it covered. */
export function useDeleteInvoiceDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteInvoiceDraft,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.invoiceablePeriods() });
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.all });
    },
  });
}

export function useIssueInvoice(invoiceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => issueInvoice(invoiceId),
    onSuccess: (invoice) => {
      queryClient.setQueryData(invoiceKeys.detail(invoiceId), invoice);
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.lists() });
    },
  });
}

export function useMarkInvoicePaid(invoiceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (paidOn: string) => markInvoicePaid({ invoiceId, paidOn }),
    onSuccess: (invoice) => {
      queryClient.setQueryData(invoiceKeys.detail(invoiceId), invoice);
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.lists() });
    },
  });
}

/** Frees every billing period the voided invoice covered, so the "To invoice" tab needs
 * refreshing too. */
export function useVoidInvoice(invoiceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => voidInvoice({ invoiceId, reason }),
    onSuccess: (invoice) => {
      queryClient.setQueryData(invoiceKeys.detail(invoiceId), invoice);
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.invoiceablePeriods() });
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.lists() });
    },
  });
}
