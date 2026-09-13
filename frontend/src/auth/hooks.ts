import { notifications } from "@mantine/notifications";
import { hashKey, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { currentUserQueryKey } from "@/api/client";
import {
  changePassword,
  type CurrentUser,
  fetchCurrentUser,
  SessionNotStoredError,
  signIn,
  signOut,
} from "@/auth/api";

const currentUserQueryHash = hashKey(currentUserQueryKey);

/** The signed-in user: `null` when signed out, `undefined` until the session has been checked. */
export function useCurrentUser() {
  return useQuery({ queryKey: currentUserQueryKey, queryFn: fetchCurrentUser });
}

/** The signed-in user, for components rendered inside `RequireAuth`. */
export function useAuthenticatedUser(): CurrentUser {
  const { data } = useCurrentUser();
  if (!data) {
    throw new Error("useAuthenticatedUser() must be used inside <RequireAuth>");
  }
  return data;
}

export function useSignIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: { email: string; password: string }) => {
      await signIn(credentials);
      // Nothing cached during a previous session may leak into this one.
      queryClient.removeQueries({ predicate: (query) => query.queryHash !== currentUserQueryHash });
      const user = await queryClient.fetchQuery({
        queryKey: currentUserQueryKey,
        queryFn: fetchCurrentUser,
        staleTime: 0,
      });
      if (!user) {
        throw new SessionNotStoredError();
      }
    },
  });
}

/** Forget the session locally: drop all cached data and open the sign-in page. */
function useEndSession() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return async () => {
    queryClient.removeQueries({ predicate: (query) => query.queryHash !== currentUserQueryHash });
    queryClient.setQueryData(currentUserQueryKey, null);
    // Committing the navigation synchronously unmounts RequireAuth before it reacts to the
    // signed-out state, which would make the next sign-in return to the page left behind.
    await navigate("/login", { replace: true, flushSync: true });
  };
}

export function useSignOut() {
  const endSession = useEndSession();
  return useMutation({
    mutationFn: signOut,
    onSuccess: endSession,
    onError: () => {
      notifications.show({ color: "red", title: "Sign out failed", message: "Please try again." });
    },
  });
}

export function useChangePassword() {
  const endSession = useEndSession();
  return useMutation({
    mutationFn: async (passwords: { currentPassword: string; newPassword: string }) => {
      await changePassword(passwords);
      // The change already revoked the session; clearing its cookie is only tidying up.
      await signOut().catch(() => undefined);
    },
    onSuccess: async () => {
      await endSession();
      notifications.show({ title: "Password changed", message: "Sign in with your new password." });
    },
  });
}
