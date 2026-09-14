import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  NumberInput,
  Popover,
  Table,
  Text,
  Textarea,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";

import type { CalendarDay } from "@/calendar/api";
import { AddRowModal } from "@/timesheets/AddRowModal";
import {
  getTimesheetWeek,
  TimesheetRuleError,
  type PickedRow,
  type TimeEntryChange,
  type TimesheetRow,
} from "@/timesheets/api";
import { useSaveTimesheetWeek, useTimesheetWeek } from "@/timesheets/hooks";
import { addWeeks, formatDayLabel } from "@/timesheets/week";

const UNIT_LABEL: Record<TimesheetRow["billing_item"]["unit"], string> = {
  hour: "h",
  day: "d",
  amount: "",
};
const UNIT_STEP: Record<TimesheetRow["billing_item"]["unit"], number> = {
  hour: 0.25,
  day: 0.5,
  amount: 0.01,
};
const UNIT_MAX: Record<TimesheetRow["billing_item"]["unit"], number | undefined> = {
  hour: 24,
  day: 1,
  amount: undefined,
};
const MAX_DAILY_HOURS = 24;

type CellDraft = { quantity: number | null; note: string | null };

function cellKey(billingItemId: string, date: string): string {
  return `${billingItemId}|${date}`;
}

function rowUnitLabel(row: { billing_item: TimesheetRow["billing_item"]; project: TimesheetRow["project"] }): string {
  return row.billing_item.unit === "amount" ? row.project.customer.currency : UNIT_LABEL[row.billing_item.unit];
}

type Props = {
  userId: string;
  weekStart: string;
  onDirtyChange: (dirty: boolean) => void;
};

export function TimesheetGrid({ userId, weekStart, onDirtyChange }: Props) {
  const weekQuery = useTimesheetWeek(userId, weekStart);
  const saveWeek = useSaveTimesheetWeek(userId, weekStart);
  const [edits, setEdits] = useState<Map<string, CellDraft>>(new Map());
  const [addedRows, setAddedRows] = useState<PickedRow[]>([]);
  const [addRowOpened, { open: openAddRow, close: closeAddRow }] = useDisclosure(false);
  const [ruleError, setRuleError] = useState<string | null>(null);
  const [copyPending, setCopyPending] = useState(false);

  // Draft state (edits/addedRows/ruleError) is reset by remounting: the caller keys this
  // component by `${userId}|${weekStart}`, so switching week or user always starts fresh.
  const isDirty = edits.size > 0;
  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  const week = weekQuery.data;

  const rows = useMemo(() => {
    if (!week) return [];
    const combined: TimesheetRow[] = [...week.rows];
    for (const added of addedRows) {
      if (!combined.some((row) => row.billing_item.id === added.billing_item.id)) {
        combined.push({
          project: added.project,
          billing_item: added.billing_item,
          is_open: true,
          entries: [],
        });
      }
    }
    combined.sort(
      (a, b) =>
        a.project.name.localeCompare(b.project.name) ||
        a.billing_item.position - b.billing_item.position,
    );
    return combined;
  }, [week, addedRows]);

  if (weekQuery.isPending) return <Loader />;
  if (weekQuery.isError || !week) return <Alert color="red">Could not load the timesheet.</Alert>;

  function cellValue(row: TimesheetRow, date: string): CellDraft {
    const key = cellKey(row.billing_item.id, date);
    const draft = edits.get(key);
    if (draft) return draft;
    const entry = row.entries.find((candidate) => candidate.date === date);
    return { quantity: entry ? Number(entry.quantity) : null, note: entry?.note ?? null };
  }

  function setCell(row: TimesheetRow, date: string, patch: Partial<CellDraft>) {
    const key = cellKey(row.billing_item.id, date);
    const current = cellValue(row, date);
    setEdits((previous) => {
      const next = new Map(previous);
      next.set(key, { ...current, ...patch });
      return next;
    });
  }

  const days = week.days;
  const excludeIds = new Set(rows.map((row) => row.billing_item.id));

  function dailyHourTotal(date: string): number {
    return rows
      .filter((row) => row.billing_item.unit === "hour")
      .reduce((sum, row) => sum + (cellValue(row, date).quantity ?? 0), 0);
  }

  const weeklyHourTotal = days.reduce((sum, day) => sum + dailyHourTotal(day.day), 0);

  async function handleSave() {
    setRuleError(null);
    const changes: TimeEntryChange[] = Array.from(edits.entries()).map(([key, value]) => {
      const [billingItemId, date] = key.split("|");
      return { billing_item_id: billingItemId, date, quantity: value.quantity, note: value.note };
    });
    try {
      await saveWeek.mutateAsync(changes);
      setEdits(new Map());
      setAddedRows([]);
      notifications.show({ title: "Timesheet saved", message: "" });
    } catch (error) {
      if (error instanceof TimesheetRuleError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  function handleDiscard() {
    setEdits(new Map());
    setAddedRows([]);
    setRuleError(null);
  }

  async function handleCopyFromPreviousWeek() {
    setCopyPending(true);
    try {
      const previousWeek = await getTimesheetWeek({
        weekStart: addWeeks(weekStart, -1),
        userId,
      });
      const currentIds = new Set([...excludeIds, ...addedRows.map((row) => row.billing_item.id)]);
      const toAdd = previousWeek.rows
        .filter((row) => row.is_open && !currentIds.has(row.billing_item.id))
        .map((row) => ({ project: row.project, billing_item: row.billing_item }));
      setAddedRows((previous) => [...previous, ...toAdd]);
    } finally {
      setCopyPending(false);
    }
  }

  return (
    <>
      {ruleError && (
        <Alert color="red" mb="sm" onClose={() => setRuleError(null)} withCloseButton>
          {ruleError}
        </Alert>
      )}

      <Table.ScrollContainer minWidth={720}>
        <Table withTableBorder withColumnBorders striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Project / billing item</Table.Th>
              {days.map((day) => (
                <DayHeader key={day.day} day={day} />
              ))}
              <Table.Th>Total</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row) => (
              <RowView
                key={row.billing_item.id}
                row={row}
                days={days}
                canEdit={week.can_edit && row.is_open}
                cellValue={cellValue}
                setCell={setCell}
              />
            ))}
            {rows.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={days.length + 2}>
                  <Text c="dimmed">No rows yet. Add one to start booking time.</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
          {rows.some((row) => row.billing_item.unit === "hour") && (
            <Table.Tfoot>
              <Table.Tr>
                <Table.Th>Daily hours</Table.Th>
                {days.map((day) => {
                  const total = dailyHourTotal(day.day);
                  return (
                    <Table.Th key={day.day} c={total > MAX_DAILY_HOURS ? "red" : undefined}>
                      {total > 0 ? total.toFixed(2) : ""}
                    </Table.Th>
                  );
                })}
                <Table.Th>{weeklyHourTotal > 0 ? `${weeklyHourTotal.toFixed(2)} h` : ""}</Table.Th>
              </Table.Tr>
            </Table.Tfoot>
          )}
        </Table>
      </Table.ScrollContainer>

      <Group mt="xs" gap="xs">
        <Badge color="gray" variant="light">
          Weekend
        </Badge>
        <Badge color="orange" variant="light">
          Public holiday
        </Badge>
        <Badge color="yellow" variant="light">
          Bridge day / company day off
        </Badge>
      </Group>

      {week.can_edit && (
        <Group justify="space-between" mt="md">
          <Group>
            <Button variant="default" onClick={openAddRow}>
              Add row
            </Button>
            <Button variant="default" loading={copyPending} onClick={() => void handleCopyFromPreviousWeek()}>
              Copy rows from previous week
            </Button>
          </Group>
          <Group>
            <Button variant="default" disabled={!isDirty} onClick={handleDiscard}>
              Discard
            </Button>
            <Button disabled={!isDirty} loading={saveWeek.isPending} onClick={() => void handleSave()}>
              Save
            </Button>
          </Group>
        </Group>
      )}

      <AddRowModal
        opened={addRowOpened}
        onClose={closeAddRow}
        excludeBillingItemIds={excludeIds}
        onAdd={(picked) => setAddedRows((previous) => [...previous, picked])}
      />
    </>
  );
}

function DayHeader({ day }: { day: CalendarDay }) {
  const kind = day.non_working_day?.kind ?? (day.is_weekend ? "weekend" : "workday");
  const background =
    kind === "weekend"
      ? "var(--mantine-color-gray-light)"
      : kind === "public_holiday"
        ? "var(--mantine-color-orange-light)"
        : kind === "bridge_day" || kind === "company_day_off"
          ? "var(--mantine-color-yellow-light)"
          : undefined;
  const label = formatDayLabel(day.day);
  const th = (
    <Table.Th data-kind={kind} style={{ backgroundColor: background }}>
      {label}
    </Table.Th>
  );
  if (day.non_working_day) {
    return <Tooltip label={day.non_working_day.name}>{th}</Tooltip>;
  }
  return th;
}

function RowView({
  row,
  days,
  canEdit,
  cellValue,
  setCell,
}: {
  row: TimesheetRow;
  days: CalendarDay[];
  canEdit: boolean;
  cellValue: (row: TimesheetRow, date: string) => CellDraft;
  setCell: (row: TimesheetRow, date: string, patch: Partial<CellDraft>) => void;
}) {
  const total = days.reduce((sum, day) => sum + (cellValue(row, day.day).quantity ?? 0), 0);
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="sm" fw={500}>
          {row.billing_item.name}
        </Text>
        <Text size="xs" c="dimmed">
          {row.project.customer.name} · {row.project.name}
        </Text>
        <Group gap={4} mt={2}>
          {row.billing_item.preset !== null && (
            <Badge size="xs" variant="light">
              Default
            </Badge>
          )}
          {!row.billing_item.is_active && (
            <Badge size="xs" color="gray" variant="light">
              Archived
            </Badge>
          )}
          {!row.project.is_active && (
            <Badge size="xs" color="gray" variant="light">
              Project archived
            </Badge>
          )}
          {!row.is_open && (
            <Badge size="xs" color="gray" variant="light">
              Closed
            </Badge>
          )}
        </Group>
      </Table.Td>
      {days.map((day) => (
        <Table.Td key={day.day} data-kind={day.non_working_day?.kind ?? (day.is_weekend ? "weekend" : "workday")}>
          <Cell row={row} date={day.day} canEdit={canEdit} value={cellValue(row, day.day)} onChange={(patch) => setCell(row, day.day, patch)} />
        </Table.Td>
      ))}
      <Table.Td>{total > 0 ? `${total.toFixed(2)} ${rowUnitLabel(row)}`.trim() : ""}</Table.Td>
    </Table.Tr>
  );
}

function Cell({
  row,
  date,
  canEdit,
  value,
  onChange,
}: {
  row: TimesheetRow;
  date: string;
  canEdit: boolean;
  value: CellDraft;
  onChange: (patch: Partial<CellDraft>) => void;
}) {
  const [noteOpened, { open: openNote, close: closeNote }] = useDisclosure(false);
  const label = `${row.billing_item.name} ${date}`;

  if (!canEdit) {
    return value.quantity !== null ? (
      <Text size="sm">{value.quantity.toFixed(2)}</Text>
    ) : (
      <Text size="sm" c="dimmed">
        –
      </Text>
    );
  }

  return (
    <Group gap={4} wrap="nowrap">
      <NumberInput
        aria-label={label}
        value={value.quantity ?? ""}
        onChange={(next) => onChange({ quantity: next === "" ? null : Number(next) })}
        min={0}
        max={UNIT_MAX[row.billing_item.unit]}
        step={UNIT_STEP[row.billing_item.unit]}
        decimalScale={2}
        hideControls
        w={80}
      />
      <Popover opened={noteOpened} onClose={closeNote} withArrow>
        <Popover.Target>
          <Button
            variant={value.note ? "light" : "subtle"}
            size="compact-xs"
            px={4}
            aria-label={`Note for ${label}`}
            onClick={noteOpened ? closeNote : openNote}
          >
            {value.note ? "📝" : "+"}
          </Button>
        </Popover.Target>
        <Popover.Dropdown>
          <Textarea
            aria-label={`Note text for ${label}`}
            placeholder="Note"
            autosize
            minRows={2}
            w={220}
            value={value.note ?? ""}
            onChange={(event) => onChange({ note: event.currentTarget.value || null })}
          />
        </Popover.Dropdown>
      </Popover>
    </Group>
  );
}
