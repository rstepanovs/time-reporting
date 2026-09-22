import { Alert, Anchor, Button, Group, Loader, Stack, Table, Text, Title } from "@mantine/core";
import { useSearchParams } from "react-router";

import { accountantPackageDownloadUrl } from "@/accounting/api";
import { useAccountantPackageStatus } from "@/accounting/hooks";
import { addMonths, formatHours, formatMonthLabel, todayIso } from "@/timesheets/week";

const MONTH_PARAM_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

function currentYearMonth(): { year: number; month: number } {
  const today = todayIso();
  return { year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) };
}

function formatMonthParam(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function AccountingPage() {
  const [searchParams, setSearchParams] = useSearchParams();

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
  const query = useAccountantPackageStatus(year, month);
  const status = query.data;

  return (
    <Stack>
      <Title order={2}>Accountant package</Title>

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
        <Button
          variant="default"
          onClick={() => navigateToMonth(thisMonth.year, thisMonth.month)}
        >
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

      {query.isPending && <Loader size="sm" />}
      {query.isError && (
        <Alert color="red">Could not load the accountant package status.</Alert>
      )}

      {status && (
        <>
          {status.draft_invoice_count > 0 && (
            <Alert color="yellow" title="Draft invoices">
              {status.draft_invoice_count} draft invoice
              {status.draft_invoice_count === 1 ? "" : "s"} this month — issue
              {status.draft_invoice_count === 1 ? "s" : ""} before downloading the package, or
              they won't be included.
            </Alert>
          )}
          {status.unapproved_expense_report_count > 0 && (
            <Alert color="yellow" title="Unapproved expense reports">
              {status.unapproved_expense_report_count} expense report
              {status.unapproved_expense_report_count === 1 ? "" : "s"} this month
              {status.unapproved_expense_report_count === 1 ? " isn't" : " aren't"} approved yet,
              so won't be included.
            </Alert>
          )}
          {status.uninvoiced_sent_period_count > 0 && (
            <Alert color="yellow" title="Uninvoiced periods">
              {status.uninvoiced_sent_period_count} sent billing period
              {status.uninvoiced_sent_period_count === 1 ? "" : "s"} this month
              {status.uninvoiced_sent_period_count === 1 ? " hasn't" : " haven't"} been invoiced
              yet.
            </Alert>
          )}

          <Text c="dimmed" size="sm">
            {status.invoice_count} invoice{status.invoice_count === 1 ? "" : "s"},{" "}
            {status.expense_line_count} expense line{status.expense_line_count === 1 ? "" : "s"}
          </Text>

          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Currency</Table.Th>
                <Table.Th>Invoiced</Table.Th>
                <Table.Th>Expenses</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {status.totals.length === 0 ? (
                <Table.Tr>
                  <Table.Td colSpan={3}>
                    <Text c="dimmed" size="sm">
                      Nothing this month.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ) : (
                status.totals.map((total) => (
                  <Table.Tr key={total.currency}>
                    <Table.Td>{total.currency}</Table.Td>
                    <Table.Td>{formatHours(total.invoiced_total)}</Table.Td>
                    <Table.Td>{formatHours(total.expense_total)}</Table.Td>
                  </Table.Tr>
                ))
              )}
            </Table.Tbody>
          </Table>

          <Group>
            <Anchor href={accountantPackageDownloadUrl(year, month)} download>
              Download ZIP
            </Anchor>
          </Group>
        </>
      )}
    </Stack>
  );
}
