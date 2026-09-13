import type { UserRole } from "@/auth/api";

export const roleLabels: Record<UserRole, string> = {
  admin: "Administrator",
  project_manager: "Project manager",
  worker: "Worker",
};
