import { Text } from "@mantine/core";

import { DashboardCard } from "@/components/DashboardCard";

/** The accountant level is only a flag for now; real permissions and views arrive with the
 * invoices module. No data calls here. */
export function AccountantPlaceholderCard() {
  return (
    <DashboardCard title="Invoicing">
      <Text size="sm" c="dimmed">
        Billing and invoicing tools are coming soon. For now, managers send approved project
        months to billing from their team view.
      </Text>
    </DashboardCard>
  );
}
