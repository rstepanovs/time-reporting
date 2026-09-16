import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createBackup, getSystemConfig, getSystemStatus, listBackups } from "@/system/api";

export const systemKeys = {
  all: ["system"] as const,
  status: () => [...systemKeys.all, "status"] as const,
  config: () => [...systemKeys.all, "config"] as const,
  backups: () => [...systemKeys.all, "backups"] as const,
};

export function useSystemStatus() {
  return useQuery({ queryKey: systemKeys.status(), queryFn: getSystemStatus });
}

export function useSystemConfig() {
  return useQuery({ queryKey: systemKeys.config(), queryFn: getSystemConfig });
}

export function useBackups() {
  return useQuery({ queryKey: systemKeys.backups(), queryFn: listBackups });
}

export function useCreateBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createBackup,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: systemKeys.backups() });
      // `last_backup_at` is also part of `GetSystemStatus`.
      await queryClient.invalidateQueries({ queryKey: systemKeys.status() });
    },
  });
}
