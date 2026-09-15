import { Alert, Divider, Group, Loader, Stack, Text } from "@mantine/core";

import { DashboardCard } from "@/components/DashboardCard";
import type { CurrencyAmount } from "@/timesheets/api";
import { useMonthTimeSummary } from "@/timesheets/hooks";
import { fillRatePercent, formatHours, formatMonthLabel } from "@/timesheets/week";

type Props = {
  userId: string;
  year: number;
  month: number;
  /** Tints the card as "the current month" among the month cards. */
  highlighted?: boolean;
};

function formatExpenses(expenses: CurrencyAmount[]): string {
  if (expenses.length === 0) return "—";
  // Reusing formatHours' "drop trailing zeros" formatting for money too keeps both benefit rows
  // in the same clean style; amounts here are already per currency, never combined.
  return expenses.map((expense) => `${formatHours(expense.amount)} ${expense.currency}`).join(", ");
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Group justify="space-between" gap="xs" wrap="nowrap">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm">{value}</Text>
    </Group>
  );
}

/** One month's "My time" card: hours by preset, a fill-rate total, and the benefits (per diems,
 * expenses) that aren't hours. `userId` selects whose month to load. */
export function MonthTimeCard({ userId, year, month, highlighted }: Props) {
  const query = useMonthTimeSummary(userId, year, month);
  const title = formatMonthLabel(year, month);
  const detailsHref = `/hours?month=${year}-${String(month).padStart(2, "0")}`;

  if (query.isPending) {
    return (
      <DashboardCard title={title} highlighted={highlighted}>
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title={title} highlighted={highlighted}>
        <Alert color="red">Could not load this month.</Alert>
      </DashboardCard>
    );
  }

  const summary = query.data;
  const fillRate = fillRatePercent(summary.hours.total_hours, summary.expected_hours_to_date);
  const totalLabel = `${formatHours(summary.hours.total_hours)} / ${formatHours(summary.expected_hours_to_date)} h${
    fillRate === null ? "" : ` (${fillRate}%)`
  }`;

  return (
    <DashboardCard
      title={title}
      highlighted={highlighted}
      footer={{ label: "Details →", to: detailsHref }}
    >
      <Stack gap={4}>
        <Row label="Normal" value={`${formatHours(summary.hours.normal_hours)} h`} />
        <Row label="Overtime" value={`${formatHours(summary.hours.overtime_hours)} h`} />
        <Row label="Travel" value={`${formatHours(summary.hours.travel_hours)} h`} />
        {Number(summary.hours.other_hours) > 0 && (
          <Row label="Other" value={`${formatHours(summary.hours.other_hours)} h`} />
        )}
        <Group justify="space-between" gap="xs" wrap="nowrap" mt={2}>
          <Text size="sm" fw={600}>
            Total
          </Text>
          <Text size="sm" fw={600}>
            {totalLabel}
          </Text>
        </Group>
        <Divider my={2} />
        <Row label="Per diem" value={`${formatHours(summary.per_diem_days)} days`} />
        <Row label="Expenses" value={formatExpenses(summary.expenses)} />
      </Stack>
    </DashboardCard>
  );
}
