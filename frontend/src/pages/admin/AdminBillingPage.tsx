import { Alert, Anchor, Button, Group, Loader, Modal, Pagination, Select, Stack, Table, Text, Title } from "@mantine/core";
import { MonthPickerInput } from "@mantine/dates";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useCustomers } from "@/customers/hooks";
import { useProjects } from "@/projects/hooks";
import type { BillingPeriodListItem } from "@/timesheets/api";
import { billingPeriodExportUrl } from "@/timesheets/api";
import { useBillingPeriods, useReopenProjectBillingPeriod } from "@/timesheets/hooks";
import { formatMonthLabel } from "@/timesheets/week";

const PAGE_SIZE = 20;

function periodLabel(periodStart: string): string {
  const [year, month] = periodStart.split("-").map(Number);
  return formatMonthLabel(year, month);
}

function ReopenButton({ period }: { period: BillingPeriodListItem }) {
  const [opened, { open, close }] = useDisclosure(false);
  const reopen = useReopenProjectBillingPeriod();

  async function confirm() {
    await reopen.mutateAsync({ projectId: period.project_id, periodStart: period.period_start });
    close();
    notifications.show({ title: "Period reopened", message: period.project_name });
  }

  return (
    <>
      <Button size="xs" variant="default" color="red" onClick={open}>
        Reopen…
      </Button>
      <Modal opened={opened} onClose={close} title="Reopen billing period">
        <Stack>
          <Text size="sm">
            Reopen <strong>{period.customer_name} · {period.project_name}</strong>&apos;s{" "}
            {periodLabel(period.period_start)} period? Its entries become editable again.
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

export function AdminBillingPage() {
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [monthFrom, setMonthFrom] = useState<string | null>(null);
  const [monthTo, setMonthTo] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const customers = useCustomers({ includeInactive: true, limit: 100 });
  const projects = useProjects({
    includeInactive: true,
    limit: 100,
    customerId: customerId ?? undefined,
  });

  const periods = useBillingPeriods({
    customerId: customerId ?? undefined,
    projectId: projectId ?? undefined,
    monthFrom: monthFrom ?? undefined,
    monthTo: monthTo ?? undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  function resetToFirstPage() {
    setPage(1);
  }

  const totalPages = periods.data ? Math.ceil(periods.data.total / PAGE_SIZE) : 0;

  return (
    <Stack>
      <Title order={2}>Billing</Title>

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
            setProjectId(null);
            resetToFirstPage();
          }}
          w={220}
        />
        <Select
          label="Project"
          placeholder="All projects"
          clearable
          searchable
          data={(projects.data?.items ?? []).map((project) => ({
            value: project.id,
            label: project.name,
          }))}
          value={projectId}
          onChange={(value) => {
            setProjectId(value);
            resetToFirstPage();
          }}
          w={220}
        />
        <MonthPickerInput
          label="From"
          placeholder="Any"
          clearable
          value={monthFrom}
          onChange={(value) => {
            setMonthFrom(value);
            resetToFirstPage();
          }}
          w={160}
        />
        <MonthPickerInput
          label="To"
          placeholder="Any"
          clearable
          value={monthTo}
          onChange={(value) => {
            setMonthTo(value);
            resetToFirstPage();
          }}
          w={160}
        />
      </Group>

      {periods.isPending && <Loader />}
      {periods.isError && <Alert color="red">Could not load billing periods.</Alert>}

      {periods.data && (
        <>
          {periods.data.items.length === 0 ? (
            <Text c="dimmed">No billing periods found.</Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Customer</Table.Th>
                  <Table.Th>Project</Table.Th>
                  <Table.Th>Period</Table.Th>
                  <Table.Th>Sent at</Table.Th>
                  <Table.Th>Sent by</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {periods.data.items.map((period) => (
                  <Table.Tr key={`${period.project_id}-${period.period_start}`}>
                    <Table.Td>{period.customer_name}</Table.Td>
                    <Table.Td>{period.project_name}</Table.Td>
                    <Table.Td>{periodLabel(period.period_start)}</Table.Td>
                    <Table.Td>{new Date(period.sent_at).toLocaleString()}</Table.Td>
                    <Table.Td>{period.sent_by_name}</Table.Td>
                    <Table.Td>
                      <Group gap="xs" justify="flex-end" wrap="nowrap">
                        <Anchor
                          size="sm"
                          href={billingPeriodExportUrl(period.project_id, period.period_start)}
                          download
                        >
                          CSV
                        </Anchor>
                        <ReopenButton period={period} />
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
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
