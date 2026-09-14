import { useQuery } from "@tanstack/react-query";

import { searchUserDirectory } from "@/users/api";

/** Debounce `search` in the caller; this hook just runs the query as given. */
export function useUserDirectory(search: string) {
  return useQuery({
    queryKey: ["users", "directory", search],
    queryFn: () => searchUserDirectory({ search: search || undefined, limit: 20 }),
  });
}
