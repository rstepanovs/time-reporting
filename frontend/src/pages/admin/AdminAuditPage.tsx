import { Alert, Group, Loader, Pagination, Select, Stack, Table, Text, Title, UnstyledButton } from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";

import type { AuditAction, AuditEvent } from "@/audit/api";
import { useAuditEvents } from "@/audit/hooks";
import { useUserDirectory } from "@/users/hooks";

const PAGE_SIZE = 20;

const ACTION_LABELS: Record<AuditAction, string> = {
  "user.created": "User created",
  "user.roles_changed": "User roles changed",
  "user.activated": "User activated",
  "user.deactivated": "User deactivated",
  "user.password_reset": "Password reset",
  "user.deleted": "User deleted",
  "customer.archived": "Customer archived",
  "customer.deleted": "Customer deleted",
  "project.archived": "Project archived",
  "project.deleted": "Project deleted",
  "billing_period.sent": "Billing period sent",
  "billing_period.reopened": "Billing period reopened",
  "calendar.public_holidays_imported": "Public holidays imported",
  "backup.created": "Backup created",
  "expense_report.approved": "Expense report approved",
  "expense_report.returned": "Expense report returned",
  "company.updated": "Company settings updated",
  "invoice.created": "Invoice draft created",
  "invoice.deleted": "Invoice draft deleted",
  "invoice.issued": "Invoice issued",
  "invoice.paid": "Invoice marked paid",
  "invoice.voided": "Invoice voided",
};

const ACTION_OPTIONS = (Object.keys(ACTION_LABELS) as AuditAction[]).map((value) => ({
  value,
  label: ACTION_LABELS[value],
}));

// The entity types any currently-instrumented command records — a plain string on the backend
// (see `audit/CLAUDE.md`), not an enum, so this list is this page's own convenience, not derived
// from the schema.
const ENTITY_TYPE_LABELS: Record<string, string> = {
  user: "User",
  customer: "Customer",
  project: "Project",
  billing_period: "Billing period",
  calendar: "Calendar",
  backup: "Backup",
  company: "Company",
};

const ENTITY_TYPE_OPTIONS = Object.entries(ENTITY_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

function toRangeStart(date: string): string {
  return `${date}T00:00:00.000Z`;
}

function toRangeEnd(date: string): string {
  return `${date}T23:59:59.999Z`;
}

function DetailsRow({ event }: { event: AuditEvent }) {
  return (
    <Table.Tr>
      <Table.Td colSpan={4}>
        <Text
          component="pre"
          size="xs"
          c="dimmed"
          style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0 }}
        >
          {JSON.stringify(event.details, null, 2)}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}

function EventRow({ event }: { event: AuditEvent }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails = event.details !== null;

  return (
    <>
      <Table.Tr>
        <Table.Td>
          <UnstyledButton
            onClick={hasDetails ? () => setExpanded((value) => !value) : undefined}
            disabled={!hasDetails}
            aria-expanded={hasDetails ? expanded : undefined}
            aria-label={`${expanded ? "Collapse" : "Expand"} details`}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Text
              component="span"
              size="xs"
              style={{ visibility: hasDetails ? "visible" : "hidden" }}
            >
              {expanded ? "▾" : "▸"}
            </Text>
            <Text component="span" size="sm">
              {new Date(event.occurred_at).toLocaleString()}
            </Text>
          </UnstyledButton>
        </Table.Td>
        <Table.Td>{event.actor_name ?? "—"}</Table.Td>
        <Table.Td>{ACTION_LABELS[event.action]}</Table.Td>
        <Table.Td>{event.summary}</Table.Td>
      </Table.Tr>
      {expanded && <DetailsRow event={event} />}
    </>
  );
}

export function AdminAuditPage() {
  const [action, setAction] = useState<string | null>(null);
  const [entityType, setEntityType] = useState<string | null>(null);
  const [actorId, setActorId] = useState<string | null>(null);
  const [actorSearch, setActorSearch] = useState("");
  const [dateFrom, setDateFrom] = useState<string | null>(null);
  const [dateTo, setDateTo] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const [debouncedActorSearch] = useDebouncedValue(actorSearch, 300);
  const actorDirectory = useUserDirectory(debouncedActorSearch);

  const events = useAuditEvents({
    action: (action as AuditAction | null) ?? undefined,
    entityType: entityType ?? undefined,
    actorId: actorId ?? undefined,
    occurredFrom: dateFrom ? toRangeStart(dateFrom) : undefined,
    occurredTo: dateTo ? toRangeEnd(dateTo) : undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  function resetToFirstPage() {
    setPage(1);
  }

  const totalPages = events.data ? Math.ceil(events.data.total / PAGE_SIZE) : 0;

  return (
    <Stack>
      <Title order={2}>Audit log</Title>

      <Group align="flex-end">
        <Select
          label="Action"
          placeholder="Any action"
          clearable
          searchable
          data={ACTION_OPTIONS}
          value={action}
          onChange={(value) => {
            setAction(value);
            resetToFirstPage();
          }}
          w={220}
        />
        <Select
          label="Entity type"
          placeholder="Any entity"
          clearable
          data={ENTITY_TYPE_OPTIONS}
          value={entityType}
          onChange={(value) => {
            setEntityType(value);
            resetToFirstPage();
          }}
          w={180}
        />
        <Select
          label="Actor"
          placeholder="Any actor"
          clearable
          searchable
          data={(actorDirectory.data ?? []).map((candidate) => ({
            value: candidate.id,
            label: candidate.name,
          }))}
          value={actorId}
          onChange={(value) => {
            setActorId(value);
            resetToFirstPage();
          }}
          onSearchChange={setActorSearch}
          w={200}
        />
        <DatePickerInput
          label="From"
          placeholder="Any"
          clearable
          value={dateFrom}
          onChange={(value) => {
            setDateFrom(value);
            resetToFirstPage();
          }}
          w={160}
        />
        <DatePickerInput
          label="To"
          placeholder="Any"
          clearable
          value={dateTo}
          onChange={(value) => {
            setDateTo(value);
            resetToFirstPage();
          }}
          w={160}
        />
      </Group>

      {events.isPending && <Loader />}
      {events.isError && <Alert color="red">Could not load audit events.</Alert>}

      {events.data && (
        <>
          {events.data.items.length === 0 ? (
            <Text c="dimmed">No audit events found.</Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Time</Table.Th>
                  <Table.Th>Actor</Table.Th>
                  <Table.Th>Action</Table.Th>
                  <Table.Th>Summary</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {events.data.items.map((event) => (
                  <EventRow key={event.id} event={event} />
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
