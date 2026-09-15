import { Alert, Loader, Table, Text } from "@mantine/core";

import { DashboardCard } from "@/components/DashboardCard";
import { useWeeklyHours } from "@/timesheets/hooks";
import { formatHours } from "@/timesheets/week";

const WEEKS_SHOWN = 6;

type Props = {
  userId: string;
};

/** Each project's hours over the same weeks WeeklyHoursChart shows (same query, same cache), so
 * "which project did those hours go to" sits right next to "how many hours". `userId` selects
 * whose weeks to load. */
export function WeeklyProjectHoursCard({ userId }: Props) {
  const query = useWeeklyHours(userId, WEEKS_SHOWN);

  if (query.isPending) {
    return (
      <DashboardCard title="Hours per project">
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title="Hours per project">
        <Alert color="red">Could not load hours per project.</Alert>
      </DashboardCard>
    );
  }

  const projects = query.data.projects;

  return (
    <DashboardCard title="Hours per project" footer={{ label: "My hours →", to: "/hours" }}>
      {projects.length === 0 ? (
        <Text size="sm" c="dimmed">
          No hours booked in the last {WEEKS_SHOWN} weeks.
        </Text>
      ) : (
        <>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Project</Table.Th>
                <Table.Th>Total</Table.Th>
                <Table.Th>Overtime</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {projects.map((project) => (
                <Table.Tr key={project.project.id}>
                  <Table.Td>
                    <Text size="sm">
                      {project.project.customer.name} · {project.project.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>{formatHours(project.totals.total_hours)}</Table.Td>
                  <Table.Td>{formatHours(project.totals.overtime_hours)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed">
            Last {WEEKS_SHOWN} weeks
          </Text>
        </>
      )}
    </DashboardCard>
  );
}
