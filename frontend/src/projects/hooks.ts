import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addProjectBillingItem,
  addProjectMember,
  createProject,
  deleteProjectBillingItem,
  getProject,
  listProjectBillingItems,
  listProjectMembers,
  listProjects,
  removeProjectMember,
  updateProject,
  updateProjectBillingItem,
} from "@/projects/api";

type ListParams = Parameters<typeof listProjects>[0];

export const projectKeys = {
  all: ["projects"] as const,
  list: (params: ListParams) => [...projectKeys.all, "list", params] as const,
  detail: (id: string) => [...projectKeys.all, "detail", id] as const,
  members: (id: string) => [...projectKeys.all, "members", id] as const,
  billingItems: (id: string, includeInactive = false) =>
    [...projectKeys.all, "billing-items", id, includeInactive] as const,
};

export function useProjects(params: ListParams) {
  return useQuery({
    queryKey: projectKeys.list(params),
    queryFn: () => listProjects(params),
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
  });
}

export function useProjectMembers(projectId: string) {
  return useQuery({
    queryKey: projectKeys.members(projectId),
    queryFn: () => listProjectMembers(projectId),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useUpdateProject(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof updateProject>[1]) => updateProject(projectId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useAddProjectMember(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => addProjectMember(projectId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useRemoveProjectMember(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeProjectMember(projectId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useProjectBillingItems(projectId: string, includeInactive = false) {
  return useQuery({
    queryKey: projectKeys.billingItems(projectId, includeInactive),
    queryFn: () => listProjectBillingItems(projectId, includeInactive),
  });
}

export function useAddProjectBillingItem(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof addProjectBillingItem>[1]) =>
      addProjectBillingItem(projectId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useUpdateProjectBillingItem(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      itemId,
      body,
    }: {
      itemId: string;
      body: Parameters<typeof updateProjectBillingItem>[2];
    }) => updateProjectBillingItem(projectId, itemId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useDeleteProjectBillingItem(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteProjectBillingItem(projectId, itemId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectKeys.all }),
  });
}
