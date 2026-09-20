import { Anchor, Stack } from "@mantine/core";
import { Link } from "react-router";

import { DashboardCard } from "@/components/DashboardCard";

const ADMIN_SHORTCUTS = [
  { to: "/admin/users", label: "Users" },
  { to: "/admin/customers", label: "Customers" },
  { to: "/admin/projects", label: "Projects" },
  { to: "/admin/calendar", label: "Calendar" },
  { to: "/admin/billing", label: "Billing" },
  { to: "/admin/company", label: "Company" },
  { to: "/admin/audit", label: "Audit log" },
  { to: "/admin/backups", label: "Backups" },
  { to: "/admin/status", label: "System status" },
];

/** Link-only shortcuts to the Administration area; no data calls here. */
export function AdminShortcutsCard() {
  return (
    <DashboardCard title="Administration">
      <Stack gap={4}>
        {ADMIN_SHORTCUTS.map((shortcut) => (
          <Anchor key={shortcut.to} component={Link} to={shortcut.to} size="sm">
            {shortcut.label}
          </Anchor>
        ))}
      </Stack>
    </DashboardCard>
  );
}
