import { Alert, Group, Loader, Stack, Table, Tabs, Text, Title } from "@mantine/core";
import { Link, useSearchParams } from "react-router";

import { useSubmittedExpenseReports } from "@/expenses/hooks";
import type { TeamScope } from "@/timesheets/api";
import { TeamScopeToggle } from "@/timesheets/TeamScopeToggle";
import { formatHours, formatWeekLabel } from "@/timesheets/week";
import { useSubmittedTimesheetWeeks } from "@/timesheets/hooks";

function TimesheetSubmissions({ scope }: { scope: TeamScope }) {
  const submissions = useSubmittedTimesheetWeeks(scope);

  if (submissions.isPending) return <Loader />;
  if (submissions.isError) return <Alert color="red">Could not load submitted timesheets.</Alert>;
  if (submissions.data.length === 0) {
    return <Text c="dimmed">No timesheets are waiting for review.</Text>;
  }

  return (
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
  );
}

function ExpenseSubmissions({ scope }: { scope: TeamScope }) {
  const submissions = useSubmittedExpenseReports(scope);

  if (submissions.isPending) return <Loader />;
  if (submissions.isError) {
    return <Alert color="red">Could not load submitted expense reports.</Alert>;
  }
  if (submissions.data.length === 0) {
    return <Text c="dimmed">No expense reports are waiting for review.</Text>;
  }

  return (
    <Table withTableBorder>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>User</Table.Th>
          <Table.Th>Project</Table.Th>
          <Table.Th>Period</Table.Th>
          <Table.Th>Submitted</Table.Th>
          <Table.Th>Total</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {submissions.data.map((report) => (
          <Table.Tr key={report.id}>
            <Table.Td>
              <Text size="sm">{report.user.name}</Text>
              <Text size="xs" c="dimmed">
                {report.user.email}
              </Text>
            </Table.Td>
            <Table.Td>
              <Text component={Link} to={`/expenses/${report.id}`}>
                {report.project.customer.name} · {report.project.name}
              </Text>
            </Table.Td>
            <Table.Td>
              {report.period_start} – {report.period_end}
            </Table.Td>
            <Table.Td>
              {report.submitted_at ? new Date(report.submitted_at).toLocaleString() : "—"}
            </Table.Td>
            <Table.Td>
              {report.total} {report.project.customer.currency}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

/** A manager's queue of timesheet weeks and expense reports awaiting review, oldest submission
 * first, split into tabs; the scope toggle applies to both. */
export function ApprovalsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const scope = (searchParams.get("scope") === "all" ? "all" : "mine") as TeamScope;
  const tab = searchParams.get("tab") === "expenses" ? "expenses" : "timesheets";

  function setScope(nextScope: TeamScope) {
    const params = new URLSearchParams(searchParams);
    params.set("scope", nextScope);
    setSearchParams(params);
  }

  function setTab(nextTab: string | null) {
    const params = new URLSearchParams(searchParams);
    params.set("tab", nextTab ?? "timesheets");
    setSearchParams(params);
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Approvals</Title>
        <TeamScopeToggle scope={scope} onScopeChange={setScope} />
      </Group>

      <Tabs value={tab} onChange={setTab}>
        <Tabs.List>
          <Tabs.Tab value="timesheets">Timesheets</Tabs.Tab>
          <Tabs.Tab value="expenses">Expenses</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="timesheets" pt="md">
          <TimesheetSubmissions scope={scope} />
        </Tabs.Panel>
        <Tabs.Panel value="expenses" pt="md">
          <ExpenseSubmissions scope={scope} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
