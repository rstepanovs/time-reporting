import type { CurrentUser, UserRole } from "@/auth/api";

export const roleLabels: Record<UserRole, string> = {
  admin: "Administrator",
  manager: "Manager",
  accountant: "Accountant",
};

/** Every account's implicit baseline: reports time, can be a project member, sees the personal
 * dashboard. Never stored, so there's no `UserRole` value for it. */
export const EMPLOYEE_LABEL = "Employee";

export function hasRole(user: CurrentUser, role: UserRole): boolean {
  return user.roles.includes(role);
}

/** Managers create/edit customers, projects and their members, and review timesheets. */
export function canManage(user: CurrentUser): boolean {
  return hasRole(user, "manager");
}

/** Only administrators manage users/calendar, permanently delete records and reach the
 * Administration area. */
export function isAdmin(user: CurrentUser): boolean {
  return hasRole(user, "admin");
}

/** A flag only for now; real permissions arrive with the invoices module. */
export function isAccountant(user: CurrentUser): boolean {
  return hasRole(user, "accountant");
}
