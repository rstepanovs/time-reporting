import { Alert, Anchor, Group, Loader, Stack, Text, Tooltip } from "@mantine/core";
import { Link } from "react-router";

import { DashboardCard } from "@/components/DashboardCard";
import type { TeamMemberWarning, TeamProject, TeamScope } from "@/timesheets/api";
import { useTeamMonthOverview } from "@/timesheets/hooks";
import { formatHours, startOfIsoWeek, todayIso } from "@/timesheets/week";

type Props = { scope: TeamScope };

const WARNING_LABEL: Record<NonNullable<TeamMemberWarning>, string> = {
  no_entries: "No time booked on this project this month",
  under_expected_hours: "Reported hours are below what's expected so far this month",
};

type StaffRow = {
  userId: string;
  name: string;
  projects: string[];
  totalHours: string;
  expectedHours: string;
  warning: TeamMemberWarning;
};

function staffRows(projects: TeamProject[] | undefined): StaffRow[] {
  const byUser = new Map<string, StaffRow>();
  for (const teamProject of projects ?? []) {
    for (const member of teamProject.members) {
      if (!member.is_member) continue;
      const existing = byUser.get(member.user.id);
      if (existing) {
        existing.projects.push(teamProject.project.name);
        existing.warning ??= member.warning;
      } else {
        byUser.set(member.user.id, {
          userId: member.user.id,
          name: member.user.name,
          projects: [teamProject.project.name],
          totalHours: member.total_hours_in_month,
          expectedHours: member.expected_hours_to_date,
          warning: member.warning,
        });
      }
    }
  }
  return Array.from(byUser.values()).sort((a, b) => a.name.localeCompare(b.name));
}

/** Everyone working on the manager's projects this month: hours reported so far versus expected,
 * flagged when there's nothing booked or the total looks low. */
export function TeamStaffCard({ scope }: Props) {
  const today = todayIso();
  const year = Number(today.slice(0, 4));
  const month = Number(today.slice(5, 7));
  const currentWeekStart = startOfIsoWeek(today);
  const query = useTeamMonthOverview(year, month, scope);

  if (query.isPending) {
    return (
      <DashboardCard title="Staff">
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title="Staff">
        <Alert color="red">Could not load your team.</Alert>
      </DashboardCard>
    );
  }

  const staff = staffRows(query.data.projects);

  if (staff.length === 0) {
    return (
      <DashboardCard title="Staff" footer={{ label: "Team overview →", to: "/team" }}>
        <Text size="sm" c="dimmed">
          No staff on your projects yet.
        </Text>
      </DashboardCard>
    );
  }

  return (
    <DashboardCard title="Staff" footer={{ label: "Team overview →", to: "/team" }}>
      <Stack gap={6}>
        {staff.map((row) => (
          <Group key={row.userId} justify="space-between" wrap="nowrap" gap="xs">
            <div>
              <Anchor
                component={Link}
                to={`/timesheet?week=${currentWeekStart}&user=${row.userId}`}
                size="sm"
              >
                {row.name}
              </Anchor>
              <Text size="xs" c="dimmed">
                {row.projects.join(", ")}
              </Text>
            </div>
            <Group gap={4} wrap="nowrap">
              <Text size="sm">
                {formatHours(row.totalHours)}/{formatHours(row.expectedHours)} h
              </Text>
              {row.warning && (
                <Tooltip label={WARNING_LABEL[row.warning]}>
                  <Text size="sm">⚠️</Text>
                </Tooltip>
              )}
            </Group>
          </Group>
        ))}
      </Stack>
    </DashboardCard>
  );
}
