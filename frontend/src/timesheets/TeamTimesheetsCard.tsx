import { Alert, Group, Loader, Stack, Text } from "@mantine/core";

import { DashboardCard } from "@/components/DashboardCard";
import type { TeamScope } from "@/timesheets/api";
import { useTeamMonthOverview } from "@/timesheets/hooks";
import { formatMonthLabel, todayIso } from "@/timesheets/week";

type Props = { scope: TeamScope };

function Row({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Group justify="space-between" gap="xs" wrap="nowrap">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" fw={600} c={color}>
        {value}
      </Text>
    </Group>
  );
}

/** How many of the manager's team's current-month member-weeks are awaiting approval, returned
 * for corrections, or not submitted yet — the dashboard's cue for what needs attention. */
export function TeamTimesheetsCard({ scope }: Props) {
  const today = todayIso();
  const year = Number(today.slice(0, 4));
  const month = Number(today.slice(5, 7));
  const query = useTeamMonthOverview(year, month, scope);
  const title = `Timesheets · ${formatMonthLabel(year, month)}`;

  if (query.isPending) {
    return (
      <DashboardCard title={title}>
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title={title}>
        <Alert color="red">Could not load your team&apos;s timesheets.</Alert>
      </DashboardCard>
    );
  }

  const { counts } = query.data;

  return (
    <DashboardCard title={title} footer={{ label: "Approvals →", to: `/approvals?scope=${scope}` }}>
      <Stack gap={4}>
        <Row
          label="Awaiting approval"
          value={counts.awaiting_approval}
          color={counts.awaiting_approval > 0 ? "orange" : undefined}
        />
        <Row label="Returned" value={counts.returned} color={counts.returned > 0 ? "red" : undefined} />
        <Row label="Not submitted" value={counts.not_submitted} />
      </Stack>
    </DashboardCard>
  );
}
