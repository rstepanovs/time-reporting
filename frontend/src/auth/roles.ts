import type { UserRole } from "@/auth/api";

export const roleLabels: Record<UserRole, string> = {
  admin: "Administrator",
  project_manager: "Project manager",
  worker: "Worker",
};

/** Administrators and project managers can create/edit customers, projects and their members. */
export function canManage(role: UserRole): boolean {
  return role === "admin" || role === "project_manager";
}
