import { Alert, Anchor, Badge, Button, Group, Loader, Modal, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { ExpenseConflictError, ExpenseRuleError, type ExpenseReportStatus } from "@/expenses/api";
import { useCreateExpenseReport, useExpenseOptions, useMyExpenseReports } from "@/expenses/hooks";
import { addMonths, formatMonthLabel, todayIso } from "@/timesheets/week";

const MONTH_PARAM_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

const STATUS_LABEL: Record<ExpenseReportStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  returned: "Returned",
};
const STATUS_COLOR: Record<ExpenseReportStatus, string> = {
  draft: "gray",
  submitted: "blue",
  approved: "green",
  returned: "orange",
};

function currentYearMonth(): { year: number; month: number } {
  const today = todayIso();
  return { year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) };
}

function formatMonthParam(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function NewReportModal({
  opened,
  onClose,
  year,
  month,
  excludeProjectIds,
}: {
  opened: boolean;
  onClose: () => void;
  year: number;
  month: number;
  excludeProjectIds: Set<string>;
}) {
  const navigate = useNavigate();
  const options = useExpenseOptions();
  const createReport = useCreateExpenseReport();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleClose() {
    setProjectId(null);
    setError(null);
    onClose();
  }

  const projectOptions = (options.data ?? [])
    .filter((option) => !excludeProjectIds.has(option.project.id))
    .map((option) => ({ value: option.project.id, label: option.project.name }));

  async function handleCreate() {
    if (!projectId) return;
    setError(null);
    try {
      const report = await createReport.mutateAsync({ projectId, year, month });
      handleClose();
      navigate(`/expenses/${report.id}`);
    } catch (createError) {
      if (createError instanceof ExpenseRuleError || createError instanceof ExpenseConflictError) {
        setError(createError.message);
        return;
      }
      throw createError;
    }
  }

  return (
    <Modal opened={opened} onClose={handleClose} title="New expense report">
      <Stack>
        <Text size="sm" c="dimmed">
          {formatMonthLabel(year, month)}
        </Text>
        <Select
          label="Project"
          placeholder={projectOptions.length === 0 ? "No projects available" : "Choose a project"}
          data={projectOptions}
          value={projectId}
          onChange={setProjectId}
          disabled={options.isPending}
        />
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={handleClose}>
            Cancel
          </Button>
          <Button onClick={() => void handleCreate()} disabled={!projectId} loading={createReport.isPending}>
            Create
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function ExpensesPage() {
  const user = useAuthenticatedUser();
  const [searchParams, setSearchParams] = useSearchParams();
  const [newReportOpened, { open: openNewReport, close: closeNewReport }] = useDisclosure(false);

  const monthParam = searchParams.get("month");
  const { year, month } =
    monthParam && MONTH_PARAM_PATTERN.test(monthParam)
      ? { year: Number(monthParam.slice(0, 4)), month: Number(monthParam.slice(5, 7)) }
      : currentYearMonth();

  function navigateToMonth(nextYear: number, nextMonth: number) {
    const params = new URLSearchParams(searchParams);
    params.set("month", formatMonthParam(nextYear, nextMonth));
    setSearchParams(params);
  }

  const thisMonth = currentYearMonth();
  const reports = useMyExpenseReports(user.id, year, month);

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>Expenses</Title>
        <Button onClick={openNewReport}>New report</Button>
      </Group>

      <Group>
        <Button
          variant="default"
          onClick={() => {
            const { year: y, month: m } = addMonths(year, month, -1);
            navigateToMonth(y, m);
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
            const { year: y, month: m } = addMonths(year, month, 1);
            navigateToMonth(y, m);
          }}
        >
          Next →
        </Button>
        <Text fw={500}>{formatMonthLabel(year, month)}</Text>
      </Group>

      {reports.isPending && <Loader />}
      {reports.isError && <Alert color="red">Could not load expense reports.</Alert>}
      {reports.data && (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Project</Table.Th>
              <Table.Th>Lines</Table.Th>
              <Table.Th>Total</Table.Th>
              <Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {reports.data.map((report) => (
              <Table.Tr key={report.id}>
                <Table.Td>
                  <Anchor component={Link} to={`/expenses/${report.id}`}>
                    {report.project.name}
                  </Anchor>
                  <Text size="xs" c="dimmed">
                    {report.project.customer.name}
                  </Text>
                </Table.Td>
                <Table.Td>{report.line_count}</Table.Td>
                <Table.Td>
                  {report.total} {report.project.customer.currency}
                </Table.Td>
                <Table.Td>
                  <Badge color={STATUS_COLOR[report.status]}>{STATUS_LABEL[report.status]}</Badge>
                </Table.Td>
              </Table.Tr>
            ))}
            {reports.data.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={4}>
                  <Text c="dimmed">No expense reports this month.</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      )}

      <NewReportModal
        opened={newReportOpened}
        onClose={closeNewReport}
        year={year}
        month={month}
        excludeProjectIds={new Set((reports.data ?? []).map((report) => report.project.id))}
      />
    </Stack>
  );
}
