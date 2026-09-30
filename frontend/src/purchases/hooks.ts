import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  discardPurchaseDocument,
  getExchangeRate,
  getPurchasesSummary,
  listPurchaseDocuments,
  registerPurchaseDocument,
  uploadPurchaseDocuments,
  type PurchaseKind,
  type PurchaseStage,
} from "@/purchases/api";

export const purchaseKeys = {
  all: ["purchases"] as const,
  // A shared prefix, for invalidating every list and the summary at once.
  documents: () => [...purchaseKeys.all, "documents"] as const,
  list: (stage?: PurchaseStage, kind?: PurchaseKind) =>
    [...purchaseKeys.documents(), "list", stage, kind] as const,
  summary: () => [...purchaseKeys.all, "summary"] as const,
  rate: (currency: string, on: string) => [...purchaseKeys.all, "rate", currency, on] as const,
};

export function usePurchaseDocuments(stage?: PurchaseStage, kind?: PurchaseKind) {
  return useQuery({
    queryKey: purchaseKeys.list(stage, kind),
    queryFn: () => listPurchaseDocuments({ stage, kind }),
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
