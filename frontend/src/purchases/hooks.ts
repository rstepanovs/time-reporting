import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  discardPurchaseDocument,
  getExchangeRate,
  getPurchaseDocument,
  getPurchasesSummary,
  listPurchaseDocuments,
  markPurchasePaid,
  markPurchaseUnpaid,
  registerPurchaseDocument,
  returnPurchaseToInbox,
  updatePurchaseDocument,
  uploadPurchaseDocuments,
  type PurchaseListParams,
} from "@/purchases/api";

export const purchaseKeys = {
  all: ["purchases"] as const,
  // A shared prefix, for invalidating every list and the summary at once.
  documents: () => [...purchaseKeys.all, "documents"] as const,
  list: (params: PurchaseListParams) => [...purchaseKeys.documents(), "list", params] as const,
  document: (documentId: string) => [...purchaseKeys.documents(), documentId] as const,
  summary: () => [...purchaseKeys.all, "summary"] as const,
  rate: (currency: string, on: string) => [...purchaseKeys.all, "rate", currency, on] as const,
};

export function usePurchaseDocuments(params: PurchaseListParams) {
  return useQuery({
    queryKey: purchaseKeys.list(params),
    queryFn: () => listPurchaseDocuments(params),
    // Keep the previous page on screen while the next one (or a new filter) loads.
    placeholderData: (previous) => previous,
  });
}

export function usePurchaseDocument(documentId: string) {
  return useQuery({
    queryKey: purchaseKeys.document(documentId),
    queryFn: () => getPurchaseDocument(documentId),
  });
}

/** Inbox/unpaid figures and the base currency. */
export function usePurchasesSummary() {
  return useQuery({ queryKey: purchaseKeys.summary(), queryFn: getPurchasesSummary });
}

/** The Riksbank rate for the live base-currency preview; `enabled` off until the form has a
 * currency and a date. A missing rate is an ordinary outcome, not retried. */
export function useExchangeRate(currency: string, on: string, enabled: boolean) {
  return useQuery({
    queryKey: purchaseKeys.rate(currency, on),
    queryFn: () => getExchangeRate({ currency, on }),
    enabled,
    retry: false,
    staleTime: Infinity,
  });
}

function useInvalidatePurchases() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: purchaseKeys.documents() });
    void queryClient.invalidateQueries({ queryKey: purchaseKeys.summary() });
  };
}

// Each `mutationFn` is wrapped rather than passed as the bare API function: TanStack Query calls it
// with a second (context) argument, which would otherwise reach the API function and its mocks.
export function useUploadPurchaseDocuments() {
  const invalidate = useInvalidatePurchases();
  return useMutation({ mutationFn: (files: File[]) => uploadPurchaseDocuments(files), onSuccess: invalidate });
}

export function useDiscardPurchaseDocument() {
  const invalidate = useInvalidatePurchases();
  return useMutation({ mutationFn: (documentId: string) => discardPurchaseDocument(documentId), onSuccess: invalidate });
}

export function useRegisterPurchaseDocument() {
  const invalidate = useInvalidatePurchases();
  return useMutation({
    mutationFn: (params: Parameters<typeof registerPurchaseDocument>[0]) =>
      registerPurchaseDocument(params),
    onSuccess: invalidate,
  });
}

export function useUpdatePurchaseDocument() {
  const invalidate = useInvalidatePurchases();
  return useMutation({
    mutationFn: (params: Parameters<typeof updatePurchaseDocument>[0]) =>
      updatePurchaseDocument(params),
    onSuccess: invalidate,
  });
}

export function useMarkPurchasePaid() {
  const invalidate = useInvalidatePurchases();
  return useMutation({
    mutationFn: (params: Parameters<typeof markPurchasePaid>[0]) => markPurchasePaid(params),
    onSuccess: invalidate,
  });
}

export function useMarkPurchaseUnpaid() {
  const invalidate = useInvalidatePurchases();
  return useMutation({
    mutationFn: (documentId: string) => markPurchaseUnpaid(documentId),
    onSuccess: invalidate,
  });
}

export function useReturnPurchaseToInbox() {
  const invalidate = useInvalidatePurchases();
  return useMutation({
    mutationFn: (documentId: string) => returnPurchaseToInbox(documentId),
    onSuccess: invalidate,
  });
}
