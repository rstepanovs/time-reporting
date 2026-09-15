import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createUser,
  listUsers,
  resetUserPassword,
  searchUserDirectory,
  updateUser,
  type User,
  type UserRole,
} from "@/users/api";

export const userKeys = {
  all: ["users"] as const,
  list: (params: Parameters<typeof listUsers>[0]) => [...userKeys.all, "list", params] as const,
  directory: (search: string, roles?: UserRole[]) =>
    [...userKeys.all, "directory", search, roles ?? []] as const,
};

/** Debounce `search` in the caller; this hook just runs the query as given. `roles` narrows the
 * picker (e.g. to admins/project managers for a project's manager field). */
export function useUserDirectory(search: string, roles?: UserRole[]) {
  return useQuery({
    queryKey: userKeys.directory(search, roles),
    queryFn: () => searchUserDirectory({ search: search || undefined, limit: 20, roles }),
  });
}

export function useUsers(params: Parameters<typeof listUsers>[0]) {
  return useQuery({
    queryKey: userKeys.list(params),
    queryFn: () => listUsers(params),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userKeys.all }),
  });
}

export function useUpdateUser(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      name?: string;
      email?: string;
      roles?: UserRole[];
      is_active?: boolean;
    }): Promise<User> => updateUser(userId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userKeys.all }),
  });
}

export function useResetUserPassword(userId: string) {
  return useMutation({
    mutationFn: (newPassword: string) => resetUserPassword(userId, newPassword),
  });
}
