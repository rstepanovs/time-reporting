import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearCompanyLogo,
  getCompanySettings,
  setCompanyLogo,
  updateCompanySettings,
  type CompanySettingsUpdateBody,
} from "@/company/api";

export const companyKeys = {
  settings: ["company", "settings"] as const,
};

export function useCompanySettings() {
  return useQuery({
    queryKey: companyKeys.settings,
    queryFn: getCompanySettings,
  });
}

export function useUpdateCompanySettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanySettingsUpdateBody) => updateCompanySettings(body),
    onSuccess: (settings) => queryClient.setQueryData(companyKeys.settings, settings),
  });
}

export function useSetCompanyLogo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => setCompanyLogo(file),
    onSuccess: (settings) => queryClient.setQueryData(companyKeys.settings, settings),
  });
}

export function useClearCompanyLogo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: clearCompanyLogo,
    onSuccess: (settings) => queryClient.setQueryData(companyKeys.settings, settings),
  });
}
