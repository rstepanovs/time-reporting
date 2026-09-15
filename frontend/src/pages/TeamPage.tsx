import { Alert, Badge, Button, Group, Loader, Modal, Stack, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useSearchParams } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { isAdmin } from "@/auth/roles";
import {
  TimesheetConflictError,
  TimesheetRuleError,
  type BillingPeriodStatus,
  type TeamProject,
  type TeamScope,
} from "@/timesheets/api";
import { TeamScopeToggle } from "@/timesheets/TeamScopeToggle";
import { TeamWeekMatrix } from "@/timesheets/TeamWeekMatrix";
import {
  useReopenProjectBillingPeriod,
  useSendProjectMonthToBilling,
  useTeamMonthOverview,
} from "@/timesheets/hooks";
import { addMonths, formatHours, formatMonthLabel, todayIso } from "@/timesheets/week";

const MONTH_PARAM_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

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

function currentYearMonth(): { year: number; month: number } {
  const today = todayIso();
  return { year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) };
}

function SendButton({ project, year, month }: { project: TeamProject; year: number; month: number }) {
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
        Send to billing
      </Button>
      <Modal opened={opened} onClose={close} title="Send to billing">
        <Stack>
          <Text size="sm">
            Send <strong>{project.project.customer.name} · {project.project.name}</strong>&apos;s{" "}
            {formatMonthLabel(year, month)} ({formatHours(project.billing.hours.total_hours)} h) to
            billing?
          </Text>
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

function ReopenButton({ project }: { project: TeamProject }) {
  const [opened, { open, close }] = useDisclosure(false);
  const reopen = useReopenProjectBillingPeriod();

  async function confirm() {
    await reopen.mutateAsync({
      projectId: project.project.id,
      periodStart: project.billing.period_start,
    });
    close();
    notifications.show({ title: "Period reopened", message: project.project.name });
  }

  return (
    <>
      <Button size="xs" variant="default" color="red" onClick={open}>
        Reopen
      </Button>
      <Modal opened={opened} onClose={close} title="Reopen billing period">
        <Stack>
          <Text size="sm">
            Reopen <strong>{project.project.customer.name} · {project.project.name}</strong>&apos;s
            sent period? Its entries become editable again.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button color="red" loading={reopen.isPending} onClick={confirm}>
              Reopen
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function ProjectSection({
  project,
  weekStarts,
  year,
  month,
}: {
  project: TeamProject;
  weekStarts: string[];
  year: number;
  month: number;
}) {
  const user = useAuthenticatedUser();
  const { billing } = project;

  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <div>
          <Text fw={600}>
            {project.project.customer.name} · {project.project.name}
          </Text>
          <Text size="xs" c="dimmed">
            {formatHours(billing.hours.total_hours)} h · Weeks{" "}
            {billing.weeks_in_scope - billing.blocking_weeks}/{billing.weeks_in_scope} approved
          </Text>
        </div>
        <Group gap="xs">
          <Badge color={STATUS_COLOR[billing.status]} variant="light">
            {STATUS_LABEL[billing.status]}
            {billing.status === "sent" && billing.sent_at && (
              <> · {new Date(billing.sent_at).toLocaleDateString()}</>
            )}
          </Badge>
          {billing.status === "ready" && <SendButton project={project} year={year} month={month} />}
          {billing.status === "sent" && isAdmin(user) && <ReopenButton project={project} />}
        </Group>
      </Group>
      <TeamWeekMatrix project={project} weekStarts={weekStarts} year={year} month={month} />
    </Stack>
  );
}

/** The full manager team view for one calendar month: every managed project's staff, week-by-week
 * timesheet status, and billing handoff. */
export function TeamPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const monthParam = searchParams.get("month");
  const { year, month } =
    monthParam && MONTH_PARAM_PATTERN.test(monthParam)
      ? { year: Number(monthParam.slice(0, 4)), month: Number(monthParam.slice(5, 7)) }
      : currentYearMonth();
  const scope = (searchParams.get("scope") === "all" ? "all" : "mine") as TeamScope;

  function navigateToMonth(nextYear: number, nextMonth: number) {
    const params = new URLSearchParams(searchParams);
    params.set("month", `${nextYear}-${String(nextMonth).padStart(2, "0")}`);
    setSearchParams(params);
  }

  function setScope(nextScope: TeamScope) {
    const params = new URLSearchParams(searchParams);
    params.set("scope", nextScope);
    setSearchParams(params);
  }

  const overview = useTeamMonthOverview(year, month, scope);
  const thisMonth = currentYearMonth();

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Team</Title>
        <TeamScopeToggle scope={scope} onScopeChange={setScope} />
      </Group>

      <Group>
        <Button
          variant="default"
          onClick={() => {
            const previous = addMonths(year, month, -1);
            navigateToMonth(previous.year, previous.month);
          }}
        >
          ← Previous
        </Button>
        <Button variant="default" onClick={() => navigateToMonth(thisMonth.year, thisMonth.month)}>
          This month
        </Button>
        <Button
          variant="default"
          onClick={() => {
            const next = addMonths(year, month, 1);
            navigateToMonth(next.year, next.month);
          }}
        >
          Next →
        </Button>
        <Text fw={500}>{formatMonthLabel(year, month)}</Text>
      </Group>

      {overview.isPending && <Loader />}
      {overview.isError && <Alert color="red">Could not load the team overview.</Alert>}
      {overview.data && overview.data.projects.length === 0 && (
        <Text c="dimmed">No managed projects.</Text>
      )}
      {overview.data &&
        overview.data.projects.map((project) => (
          <ProjectSection
            key={project.project.id}
            project={project}
            weekStarts={overview.data.weeks}
            year={year}
            month={month}
          />
        ))}
    </Stack>
  );
}
