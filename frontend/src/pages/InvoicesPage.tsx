import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { useCustomers } from "@/customers/hooks";
import { InvoiceRuleError, type InvoiceableCustomer, type InvoiceStatus } from "@/invoices/api";
import { useCreateInvoiceDraft, useInvoiceablePeriods, useInvoices } from "@/invoices/hooks";
import { formatMonthLabel, todayIso } from "@/timesheets/week";

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<InvoiceStatus, string> = {
  draft: "Draft",
  issued: "Issued",
  paid: "Paid",
  void: "Void",
};
const STATUS_COLOR: Record<InvoiceStatus, string> = {
  draft: "gray",
  issued: "blue",
  paid: "green",
  void: "red",
};
const STATUS_OPTIONS = (Object.keys(STATUS_LABEL) as InvoiceStatus[]).map((value) => ({
  value,
  label: STATUS_LABEL[value],
}));

function periodLabel(periodStart: string): string {
  const [year, month] = periodStart.split("-").map(Number);
  return formatMonthLabel(year, month);
}

function periodKey(projectId: string, periodStart: string): string {
  return `${projectId}|${periodStart}`;
}

/** One customer's invoiceable periods, with a checkbox per period (every period pre-selected —
 * the default is to invoice everything sent) and a "Create invoice" button building a draft from
 * whichever periods are still checked. */
function CustomerInvoiceableGroup({
  customer,
  onCreated,
}: {
  customer: InvoiceableCustomer;
  onCreated: (invoiceId: string) => void;
}) {
  const allKeys = customer.periods.map((period) => periodKey(period.project_id, period.period_start));
  const [selected, setSelected] = useState<Set<string>>(new Set(allKeys));
  const [error, setError] = useState<string | null>(null);
  const createDraft = useCreateInvoiceDraft();

  function togglePeriod(key: string) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function handleCreate() {
    setError(null);
    try {
      const invoice = await createDraft.mutateAsync({
        customerId: customer.customer_id,
        periods: customer.periods
          .filter((period) => selected.has(periodKey(period.project_id, period.period_start)))
          .map((period) => ({ projectId: period.project_id, periodStart: period.period_start })),
      });
      onCreated(invoice.id);
    } catch (createError) {
      if (createError instanceof InvoiceRuleError) {
        setError(createError.message);
        return;
      }
      throw createError;
    }
  }

  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Title order={4}>{customer.customer_name}</Title>
        <Button
          size="xs"
          disabled={selected.size === 0}
          loading={createDraft.isPending}
          onClick={() => void handleCreate()}
        >
          Create invoice
        </Button>
      </Group>
      {error && <Alert color="red">{error}</Alert>}
      <Table withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th />
            <Table.Th>Project</Table.Th>
            <Table.Th>Period</Table.Th>
            <Table.Th>Sent</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {customer.periods.map((period) => {
            const key = periodKey(period.project_id, period.period_start);
            return (
              <Table.Tr key={key}>
                <Table.Td>
                  <Checkbox
                    checked={selected.has(key)}
                    onChange={() => togglePeriod(key)}
                    aria-label={`${period.project_name} ${periodLabel(period.period_start)}`}
                  />
                </Table.Td>
                <Table.Td>{period.project_name}</Table.Td>
                <Table.Td>{periodLabel(period.period_start)}</Table.Td>
                <Table.Td>{new Date(period.sent_at).toLocaleDateString()}</Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

function ToInvoiceTab() {
  const periods = useInvoiceablePeriods();
  const navigate = useNavigate();

  if (periods.isPending) return <Loader />;
  if (periods.isError) return <Alert color="red">Could not load invoiceable periods.</Alert>;
  if (periods.data.length === 0) {
    return <Text c="dimmed">No billing periods are ready to invoice.</Text>;
  }

  return (
    <Stack>
      {periods.data.map((customer) => (
        <CustomerInvoiceableGroup
          key={customer.customer_id}
          customer={customer}
          onCreated={(invoiceId) => navigate(`/invoices/${invoiceId}`)}
        />
      ))}
    </Stack>
  );
}

function InvoiceListTab() {
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [status, setStatus] = useState<InvoiceStatus | null>(null);
  const [page, setPage] = useState(1);

  const customers = useCustomers({ includeInactive: true, limit: 100 });
  const invoices = useInvoices({
    customerId: customerId ?? undefined,
    status: status ?? undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  function resetToFirstPage() {
    setPage(1);
  }

  const totalPages = invoices.data ? Math.ceil(invoices.data.total / PAGE_SIZE) : 0;
  const today = todayIso();

  return (
    <Stack>
      <Group align="flex-end">
        <Select
          label="Customer"
          placeholder="All customers"
          clearable
          searchable
          data={(customers.data?.items ?? []).map((customer) => ({
            value: customer.id,
            label: customer.name,
          }))}
          value={customerId}
          onChange={(value) => {
            setCustomerId(value);
            resetToFirstPage();
          }}
          w={220}
        />
        <Select
          label="Status"
          placeholder="Any status"
          clearable
          data={STATUS_OPTIONS}
          value={status}
          onChange={(value) => {
            setStatus(value as InvoiceStatus | null);
            resetToFirstPage();
          }}
          w={160}
        />
      </Group>

      {invoices.isPending && <Loader />}
      {invoices.isError && <Alert color="red">Could not load invoices.</Alert>}

      {invoices.data && (
        <>
          {invoices.data.items.length === 0 ? (
            <Text c="dimmed">No invoices found.</Text>
          ) : (
            <Table withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Number</Table.Th>
                  <Table.Th>Customer</Table.Th>
                  <Table.Th>Date</Table.Th>
                  <Table.Th>Due date</Table.Th>
                  <Table.Th>Total</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {invoices.data.items.map((invoice) => {
                  const overdue = invoice.status === "issued" && invoice.due_date < today;
                  return (
                    <Table.Tr key={invoice.id}>
                      <Table.Td>{invoice.number ?? "—"}</Table.Td>
                      <Table.Td>{invoice.customer_name}</Table.Td>
                      <Table.Td>{invoice.invoice_date}</Table.Td>
                      <Table.Td>{invoice.due_date}</Table.Td>
                      <Table.Td>
                        {invoice.total} {invoice.currency}
                      </Table.Td>
                      <Table.Td>
                        <Badge color={overdue ? "red" : STATUS_COLOR[invoice.status]}>
                          {overdue ? "Overdue" : STATUS_LABEL[invoice.status]}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          )}
          {totalPages > 1 && (
            <Pagination value={page} onChange={setPage} total={totalPages} mt="sm" />
          )}
        </>
      )}
    </Stack>
  );
}

/** `/invoices`, accountant only: periods ready to bill on one tab, every invoice ever issued on
 * the other. */
export function InvoicesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "invoices" ? "invoices" : "to-invoice";

  function setTab(nextTab: string | null) {
    const params = new URLSearchParams(searchParams);
    params.set("tab", nextTab ?? "to-invoice");
    setSearchParams(params);
  }

  return (
    <Stack>
      <Title order={2}>Invoices</Title>

      <Tabs value={tab} onChange={setTab} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="to-invoice">To invoice</Tabs.Tab>
          <Tabs.Tab value="invoices">Invoices</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="to-invoice" pt="md">
          <ToInvoiceTab />
        </Tabs.Panel>
        <Tabs.Panel value="invoices" pt="md">
          <InvoiceListTab />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
