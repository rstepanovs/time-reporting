import { ActionIcon, Alert, Badge, Button, Group, Loader, Modal, Stack, Table, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { DashboardCard } from "@/components/DashboardCard";
import {
  TimesheetConflictError,
  TimesheetRuleError,
  type BillingPeriodStatus,
  type TeamProject,
  type TeamScope,
} from "@/timesheets/api";
import { useSendProjectMonthToBilling, useTeamMonthOverview } from "@/timesheets/hooks";
import { addMonths, formatHours, formatMonthLabel, previousMonth, todayIso } from "@/timesheets/week";

type Props = { scope: TeamScope };

const STATUS_LABEL: Record<BillingPeriodStatus, string> = {
  not_ready: "Not ready",
  ready: "Ready",
  sent: "Sent",
};
const STATUS_COLOR: Record<BillingPeriodStatus, string> = {
  not_ready: "gray",
  ready: "blue",
  sent: "green",
};

/** The previous month during a month's first 10 days (most of a month's work is usually still
 * being booked/approved then), the current month afterward; a ‹ › switch overrides either way. */
function defaultBillingMonth(): { year: number; month: number } {
  const today = todayIso();
  const year = Number(today.slice(0, 4));
  const month = Number(today.slice(5, 7));
  const day = Number(today.slice(8, 10));
  return day <= 10 ? previousMonth(year, month) : { year, month };
}

function SendToBillingButton({
  project,
  year,
  month,
}: {
  project: TeamProject;
  year: number;
  month: number;
}) {
  const [opened, { open, close }] = useDisclosure(false);
  const send = useSendProjectMonthToBilling();

  async function confirm() {
    try {
      await send.mutateAsync({ projectId: project.project.id, year, month });
      close();
      notifications.show({
        title: "Sent to billing",
        message: "Invoicing isn't implemented yet — this just records the handoff.",
      });
    } catch (error) {
      if (error instanceof TimesheetRuleError || error instanceof TimesheetConflictError) {
        notifications.show({ color: "red", title: "Could not send", message: error.message });
        close();
      } else {
        throw error;
      }
    }
  }

  return (
    <>
      <Button size="xs" onClick={open}>
        Send →
      </Button>
      <Modal opened={opened} onClose={close} title="Send to billing">
        <Stack>
          <Text size="sm">
            Send <strong>{project.project.customer.name} · {project.project.name}</strong>&apos;s{" "}
            {formatMonthLabel(year, month)} to billing?
          </Text>
          <Table withTableBorder>
            <Table.Tbody>
              <Table.Tr>
                <Table.Td>Hours</Table.Td>
                <Table.Td>{formatHours(project.billing.hours.total_hours)} h</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>Per diem</Table.Td>
                <Table.Td>{formatHours(project.billing.per_diem_days)} days</Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>Expenses</Table.Td>
                <Table.Td>
                  {project.billing.expenses.length === 0
                    ? "—"
                    : project.billing.expenses
                        .map((expense) => `${formatHours(expense.amount)} ${expense.currency}`)
                        .join(", ")}
                </Table.Td>
              </Table.Tr>
            </Table.Tbody>
          </Table>
          <Text size="sm" c="dimmed">
            This locks the period: entries in {formatMonthLabel(year, month)} on this project can
            no longer be changed unless an admin reopens it.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button loading={send.isPending} onClick={confirm}>
              Send
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

/** Every managed project's billing-handoff status for one calendar month, with a "Send to
 * billing" action once a project is ready. */
export function ProjectBillingCard({ scope }: Props) {
  const [{ year, month }, setMonth] = useState(defaultBillingMonth);
  const query = useTeamMonthOverview(year, month, scope);

  return (
    <DashboardCard title="Billing">
      <Group justify="space-between" mb={4} wrap="nowrap">
        <ActionIcon
          variant="subtle"
          size="sm"
          aria-label="Previous month"
          onClick={() => setMonth(previousMonth(year, month))}
        >
          ‹
        </ActionIcon>
        <Text size="sm" fw={500}>
          {formatMonthLabel(year, month)}
        </Text>
        <ActionIcon
          variant="subtle"
          size="sm"
          aria-label="Next month"
          onClick={() => setMonth(addMonths(year, month, 1))}
        >
          ›
        </ActionIcon>
      </Group>

      {query.isPending && <Loader size="sm" />}
      {(query.isError || (!query.isPending && !query.data)) && (
        <Alert color="red">Could not load billing status.</Alert>
      )}
      {query.data && query.data.projects.length === 0 && (
        <Text size="sm" c="dimmed">
          No managed projects.
        </Text>
      )}
      {query.data && query.data.projects.length > 0 && (
        <Stack gap={6}>
          {query.data.projects.map((teamProject) => (
            <Group key={teamProject.project.id} justify="space-between" wrap="nowrap" gap="xs">
              <div>
                <Text size="sm">
                  {teamProject.project.customer.name} · {teamProject.project.name}
                </Text>
                <Text size="xs" c="dimmed">
                  {formatHours(teamProject.billing.hours.total_hours)} h · Weeks{" "}
                  {teamProject.billing.weeks_in_scope - teamProject.billing.blocking_weeks}/
                  {teamProject.billing.weeks_in_scope} approved
                </Text>
              </div>
              {teamProject.billing.status === "ready" ? (
                <SendToBillingButton project={teamProject} year={year} month={month} />
              ) : (
                <Badge color={STATUS_COLOR[teamProject.billing.status]} variant="light">
                  {STATUS_LABEL[teamProject.billing.status]}
                </Badge>
              )}
            </Group>
          ))}
        </Stack>
      )}
    </DashboardCard>
  );
}
