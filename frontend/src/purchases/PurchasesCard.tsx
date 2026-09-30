import { Alert, Group, Loader, Stack, Text } from "@mantine/core";

import { DashboardCard } from "@/components/DashboardCard";
import { usePurchasesSummary } from "@/purchases/hooks";

function Row({
  label,
  value,
  warn,
}: {
  label: string;
  value: string;
  warn?: boolean;
}) {
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

function formatTotal(total: string, currency: string, provisional: boolean): string {
  const amount = Number(total).toLocaleString("sv-SE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${provisional ? "~" : ""}${amount} ${currency}`;
}

/** The dashboard's "Bills to pay" card: documents waiting in the inbox and the unpaid invoices —
 * how many, their total in the base currency (marked `~` while any term is an estimate), how many
 * are overdue and how many fall due within the week. One aggregate query
 * (`purchases.GetPurchasesSummary`). */
export function PurchasesCard() {
  const query = usePurchasesSummary();

  if (query.isPending) {
    return (
      <DashboardCard title="Bills to pay">
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title="Bills to pay">
        <Alert color="red">Could not load the purchases summary.</Alert>
      </DashboardCard>
    );
  }

  const summary = query.data;
  const attention = summary.overdue_count > 0 || summary.inbox_count > 0;

  return (
    <DashboardCard
      title="Bills to pay"
      footer={{ label: "Details →", to: "/purchases?tab=to-pay" }}
      highlighted={summary.overdue_count > 0}
    >
      <Stack gap={4}>
        <Row label="Inbox" value={String(summary.inbox_count)} warn={summary.inbox_count > 0} />
        <Row label="Unpaid" value={String(summary.unpaid_count)} />
        <Row
          label="Unpaid total"
          value={formatTotal(
            summary.unpaid_total_base,
            summary.base_currency,
            summary.unpaid_provisional,
          )}
        />
        <Row
          label="Overdue"
          value={String(summary.overdue_count)}
          warn={summary.overdue_count > 0}
        />
        <Row label="Due within 7 days" value={String(summary.due_soon_count)} />
      </Stack>
      {summary.unpaid_unconverted_count > 0 && (
        <Text size="xs" c="orange">
          {summary.unpaid_unconverted_count} unpaid document
          {summary.unpaid_unconverted_count === 1 ? " has" : "s have"} no {summary.base_currency}{" "}
          amount yet and {summary.unpaid_unconverted_count === 1 ? "isn't" : "aren't"} in the total.
        </Text>
      )}
      {!attention && (
        <Text size="xs" c="dimmed">
          Nothing needs attention.
        </Text>
      )}
    </DashboardCard>
  );
}
