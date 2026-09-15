import { Alert, Loader, Stack, Table, Text, Title } from "@mantine/core";
import { Link } from "react-router";

import { formatHours, formatWeekLabel } from "@/timesheets/week";
import { useSubmittedTimesheetWeeks } from "@/timesheets/hooks";

/** A manager's queue of weeks awaiting review, oldest submission first. */
export function ApprovalsPage() {
  const submissions = useSubmittedTimesheetWeeks();

  return (
    <Stack>
      <Title order={2}>Approvals</Title>

      {submissions.isPending && <Loader />}
      {submissions.isError && <Alert color="red">Could not load submitted timesheets.</Alert>}
      {submissions.data && submissions.data.length === 0 && (
        <Text c="dimmed">No timesheets are waiting for review.</Text>
      )}
      {submissions.data && submissions.data.length > 0 && (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>User</Table.Th>
              <Table.Th>Week</Table.Th>
              <Table.Th>Submitted</Table.Th>
              <Table.Th>Hours</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {submissions.data.map((submission) => (
              <Table.Tr key={`${submission.user.id}|${submission.week_start}`}>
                <Table.Td>
                  <Text size="sm">{submission.user.name}</Text>
                  <Text size="xs" c="dimmed">
                    {submission.user.email}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text
                    component={Link}
                    to={`/timesheet?week=${submission.week_start}&user=${submission.user.id}`}
                  >
                    {formatWeekLabel(submission.week_start)}
                  </Text>
                </Table.Td>
                <Table.Td>{new Date(submission.submitted_at).toLocaleString()}</Table.Td>
                <Table.Td>{formatHours(submission.total_hours)} h</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
