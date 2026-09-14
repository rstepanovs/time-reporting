import { Outlet } from "react-router";

import type { UserRole } from "@/auth/api";
import { useAuthenticatedUser } from "@/auth/hooks";
import { NotFoundPage } from "@/pages/NotFoundPage";

/** Renders child routes only for a signed-in user with one of `roles`; everyone else sees the
 * same not-found page a nonexistent route would show, so the section's existence isn't revealed.
 * Must be nested inside `RequireAuth`. */
export function RequireRole({ roles }: { roles: UserRole[] }) {
  const user = useAuthenticatedUser();
  if (!roles.includes(user.role)) {
    return <NotFoundPage />;
  }
  return <Outlet />;
}
