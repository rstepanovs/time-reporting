import { useQuery } from "@tanstack/react-query";

import { getSystemConfig, getSystemStatus } from "@/system/api";

export const systemKeys = {
  all: ["system"] as const,
  status: () => [...systemKeys.all, "status"] as const,
  config: () => [...systemKeys.all, "config"] as const,
};

export function useSystemStatus() {
  return useQuery({ queryKey: systemKeys.status(), queryFn: getSystemStatus });
}

export function useSystemConfig() {
  return useQuery({ queryKey: systemKeys.config(), queryFn: getSystemConfig });
}
