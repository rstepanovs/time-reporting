import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getRemovalImpact, type RemovableEntity, removeEntity } from "@/admin/api";

export const adminKeys = {
  impact: (entity: RemovableEntity, id: string) => ["admin", entity, id, "removal-impact"] as const,
};

/** Fetches the removal impact only while `enabled` (typically: while the dialog is open). */
export function useRemovalImpact(
  entity: RemovableEntity,
  id: string,
  options: { enabled: boolean },
) {
  return useQuery({
    queryKey: adminKeys.impact(entity, id),
    queryFn: () => getRemovalImpact(entity, id),
    enabled: options.enabled,
  });
}

export function useRemoveEntity(entity: RemovableEntity) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, permanent }: { id: string; permanent: boolean }) =>
      removeEntity(entity, id, { permanent }),
    onSuccess: async () => {
      // "users" / "customers" / "projects" are also each list's own top-level query key.
      await queryClient.invalidateQueries({ queryKey: [entity] });
      // Users and customers show up on the projects pages (member lists, customer name/status).
      if (entity !== "projects") {
        await queryClient.invalidateQueries({ queryKey: ["projects"] });
      }
    },
  });
}
