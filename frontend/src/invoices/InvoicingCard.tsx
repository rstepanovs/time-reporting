import { Alert, Group, Loader, Stack, Text } from "@mantine/core";

import { DashboardCard } from "@/components/DashboardCard";
import type { CurrencyTotal } from "@/invoices/api";
import { useInvoicingSummary } from "@/invoices/hooks";
import { formatHours } from "@/timesheets/week";

function formatTotals(totals: CurrencyTotal[]): string {
  if (totals.length === 0) return "—";
  // Reusing formatHours' "drop trailing zeros" formatting for money too, following
  // `MonthTimeCard.formatExpenses` — amounts here are already per currency, never combined.
  return totals.map((total) => `${formatHours(total.amount)} ${total.currency}`).join(", ");
}

function Row({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <Group justify="space-between" gap="xs" wrap="nowrap">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" c={warn ? "red" : undefined} fw={warn ? 600 : undefined}>
        {value}
      </Text>
    </Group>
  );
}

/** The dashboard's "Billing" section: periods still waiting to be invoiced, the unpaid total per
 * currency and an overdue count, all from one aggregate query
 * (`invoices.GetInvoicingSummary`) rather than paging through every invoice/period here. */
export function InvoicingCard() {
  const query = useInvoicingSummary();

  if (query.isPending) {
    return (
      <DashboardCard title="Invoicing">
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title="Invoicing">
        <Alert color="red">Could not load the invoicing summary.</Alert>
      </DashboardCard>
    );
  }

  const summary = query.data;

  return (
    <DashboardCard title="Invoicing" footer={{ label: "Details →", to: "/invoices" }}>
      <Stack gap={4}>
        <Row label="Periods to invoice" value={String(summary.periods_to_invoice)} />
        <Row label="Unpaid" value={formatTotals(summary.unpaid_totals)} />
        <Row
          label="Overdue"
          value={String(summary.overdue_count)}
          warn={summary.overdue_count > 0}
        />
      </Stack>
    </DashboardCard>
  );
}
