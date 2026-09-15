import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  NumberInput,
  Popover,
  Stack,
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
  TimesheetConflictError,
  TimesheetRuleError,
  type PickedRow,
  type RowCommentChange,
  type TimeEntryChange,
  type TimesheetOption,
  type TimesheetRow,
  type TimesheetWeek,
} from "@/timesheets/api";
import { dayKind, dayKindBackground } from "@/timesheets/dayKind";
import {
  useApproveTimesheetWeek,
  useReturnTimesheetWeek,
  useSaveTimesheetWeek,
  useSubmitTimesheetWeek,
  useTimesheetOptions,
  useTimesheetWeek,
} from "@/timesheets/hooks";
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

const STATUS_LABEL: Record<TimesheetWeek["status"], string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  returned: "Returned",
};
const STATUS_COLOR: Record<TimesheetWeek["status"], string> = {
  draft: "gray",
  submitted: "blue",
  approved: "green",
  returned: "orange",
};

type CellDraft = { quantity: number | null; note: string | null };

function cellKey(billingItemId: string, date: string): string {
  return `${billingItemId}|${date}`;
}

/** Drop every entry of `map` whose key belongs to `billingItemId` (used when a row is removed so
 * its pending cell edits don't leak into the next Save). */
function pruneBillingItem<T>(map: Map<string, T>, billingItemId: string): Map<string, T> {
  const next = new Map(map);
  const prefix = `${billingItemId}|`;
  for (const key of next.keys()) {
    if (key.startsWith(prefix)) next.delete(key);
  }
  return next;
}

function rowUnitLabel(row: { billing_item: TimesheetRow["billing_item"]; project: TimesheetRow["project"] }): string {
  return row.billing_item.unit === "amount" ? row.project.customer.currency : UNIT_LABEL[row.billing_item.unit];
}

/** If `week` is an untouched draft, the caller has exactly one open project, and it has an active
 * "normal hours" item, pre-fill every working day of the week with that project's
 * `normal_working_hours` — a fresh week usually just repeats the same normal day. Returns `null`
 * when none of that applies (multiple/no open projects, a non-draft week, or one that already has
 * rows), in which case the grid starts empty as before. */
function computePrefill(
  week: TimesheetWeek,
  options: TimesheetOption[] | undefined,
): { row: PickedRow; edits: Map<string, CellDraft> } | null {
  if (week.status !== "draft" || !week.can_edit || week.rows.length > 0) return null;
  if (!options || options.length !== 1) return null;
  const option = options[0];
  const normalItem = option.billing_items.find(
    (item) => item.preset === "normal_hours" && item.is_active,
  );
  if (!normalItem) return null;

  const edits = new Map<string, CellDraft>();
  for (const day of week.days) {
    if (day.is_weekend || day.non_working_day) continue;
    edits.set(cellKey(normalItem.id, day.day), {
      quantity: Number(option.project.normal_working_hours),
      note: null,
    });
  }
  if (edits.size === 0) return null;
  return { row: { project: option.project, billing_item: normalItem }, edits };
}

type Props = {
  userId: string;
  weekStart: string;
  onDirtyChange: (dirty: boolean) => void;
};

export function TimesheetGrid({ userId, weekStart, onDirtyChange }: Props) {
  const weekQuery = useTimesheetWeek(userId, weekStart);
  const optionsQuery = useTimesheetOptions();
  const saveWeek = useSaveTimesheetWeek(userId, weekStart);
  const submitWeek = useSubmitTimesheetWeek(userId, weekStart);
  const approveWeek = useApproveTimesheetWeek(userId, weekStart);
  const returnWeek = useReturnTimesheetWeek(userId, weekStart);

  const [edits, setEdits] = useState<Map<string, CellDraft>>(new Map());
  const [commentEdits, setCommentEdits] = useState<Map<string, string | null>>(new Map());
  const [deletedRows, setDeletedRows] = useState<Set<string>>(new Set());
  const [addedRows, setAddedRows] = useState<PickedRow[]>([]);
  const [prefillRow, setPrefillRow] = useState<PickedRow | null>(null);
  const [prefillEdits, setPrefillEdits] = useState<Map<string, CellDraft>>(new Map());
  const [prefillComputed, setPrefillComputed] = useState(false);

  const [addRowOpened, { open: openAddRow, close: closeAddRow }] = useDisclosure(false);
  const [submitConfirmOpened, { open: openSubmitConfirm, close: closeSubmitConfirm }] =
    useDisclosure(false);
  const [returnOpened, { open: openReturn, close: closeReturn }] = useDisclosure(false);
  const [returnComment, setReturnComment] = useState("");
  const [ruleError, setRuleError] = useState<string | null>(null);
  const [copyPending, setCopyPending] = useState(false);

  // Draft state is reset by remounting: the caller keys this component by `${userId}|${weekStart}`,
  // so switching week or user always starts fresh.
  const isDirty = edits.size > 0 || commentEdits.size > 0 || deletedRows.size > 0;
  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  const week = weekQuery.data;

  const rows = useMemo(() => {
    if (!week) return [];
    const combined: TimesheetRow[] = week.rows.filter(
      (row) => !deletedRows.has(row.billing_item.id),
    );
    const draftRows = prefillRow ? [prefillRow, ...addedRows] : addedRows;
    for (const added of draftRows) {
      if (!combined.some((row) => row.billing_item.id === added.billing_item.id)) {
        combined.push({
          project: added.project,
          billing_item: added.billing_item,
          is_open: true,
          entries: [],
          comment: null,
        });
      }
    }
    combined.sort(
      (a, b) =>
        a.project.name.localeCompare(b.project.name) ||
        a.billing_item.position - b.billing_item.position,
    );
    return combined;
  }, [week, addedRows, prefillRow, deletedRows]);

  if (weekQuery.isPending) return <Loader />;
  if (weekQuery.isError || !week) return <Alert color="red">Could not load the timesheet.</Alert>;

  // Compute the prefill once the week and the options have both loaded, and only ever once per
  // mount — so it never re-appears after the user (or a save) changes the week's rows. Calling
  // setState directly here (React's "adjusting state during rendering" pattern) rather than in an
  // effect avoids an extra render pass; the `prefillComputed` guard keeps it from looping.
  if (!prefillComputed && !optionsQuery.isPending) {
    const prefill = computePrefill(week, optionsQuery.data);
    setPrefillComputed(true);
    if (prefill) {
      setPrefillRow(prefill.row);
      setPrefillEdits(prefill.edits);
    }
  }

  function cellValue(row: TimesheetRow, date: string): CellDraft {
    const key = cellKey(row.billing_item.id, date);
    const draft = edits.get(key);
    if (draft) return draft;
    const prefillDraft = prefillEdits.get(key);
    if (prefillDraft) return prefillDraft;
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

  function rowComment(row: TimesheetRow): string | null {
    return commentEdits.has(row.billing_item.id)
      ? (commentEdits.get(row.billing_item.id) ?? null)
      : row.comment;
  }

  function setRowComment(row: TimesheetRow, comment: string) {
    setCommentEdits((previous) => {
      const next = new Map(previous);
      next.set(row.billing_item.id, comment || null);
      return next;
    });
  }

  function handleDeleteRow(row: TimesheetRow) {
    const billingItemId = row.billing_item.id;
    if (week?.rows.some((candidate) => candidate.billing_item.id === billingItemId)) {
      setDeletedRows((previous) => new Set(previous).add(billingItemId));
    } else if (prefillRow?.billing_item.id === billingItemId) {
      setPrefillRow(null);
      setPrefillEdits(new Map());
    } else {
      setAddedRows((previous) => previous.filter((r) => r.billing_item.id !== billingItemId));
    }
    setEdits((previous) => pruneBillingItem(previous, billingItemId));
    setCommentEdits((previous) => {
      const next = new Map(previous);
      next.delete(billingItemId);
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
  const hasPendingPrefill = prefillEdits.size > 0;

  /** Build the change/comment batch for everything currently pending (manual edits, unsaved
   * prefill, and rows marked for deletion) and save it, resetting all draft state on success. */
  async function persistDraft(): Promise<void> {
    if (!week) return;
    const changes: TimeEntryChange[] = [];
    for (const [key, value] of edits.entries()) {
      const [billingItemId, date] = key.split("|");
      changes.push({ billing_item_id: billingItemId, date, quantity: value.quantity, note: value.note });
    }
    for (const [key, value] of prefillEdits.entries()) {
      if (edits.has(key)) continue;
      const [billingItemId, date] = key.split("|");
      changes.push({ billing_item_id: billingItemId, date, quantity: value.quantity, note: value.note });
    }
    const rowComments: RowCommentChange[] = Array.from(commentEdits.entries()).map(
      ([billingItemId, comment]) => ({ billing_item_id: billingItemId, comment }),
    );
    for (const billingItemId of deletedRows) {
      const row = week.rows.find((candidate) => candidate.billing_item.id === billingItemId);
      if (!row) continue;
      for (const entry of row.entries) {
        changes.push({ billing_item_id: billingItemId, date: entry.date, quantity: null });
      }
      if (row.comment !== null && !commentEdits.has(billingItemId)) {
        rowComments.push({ billing_item_id: billingItemId, comment: null });
      }
    }

    await saveWeek.mutateAsync({ changes, rowComments });
    setEdits(new Map());
    setAddedRows([]);
    setCommentEdits(new Map());
    setDeletedRows(new Set());
    setPrefillRow(null);
    setPrefillEdits(new Map());
  }

  async function handleSave() {
    setRuleError(null);
    try {
      await persistDraft();
      notifications.show({ title: "Timesheet saved", message: "" });
    } catch (error) {
      if (error instanceof TimesheetRuleError || error instanceof TimesheetConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  function handleDiscard() {
    setEdits(new Map());
    setCommentEdits(new Map());
    setDeletedRows(new Set());
    setRuleError(null);
  }

  async function handleConfirmSubmit() {
    setRuleError(null);
    try {
      if (isDirty || hasPendingPrefill) {
        await persistDraft();
      }
      await submitWeek.mutateAsync();
      closeSubmitConfirm();
      notifications.show({ title: "Timesheet submitted", message: "" });
    } catch (error) {
      if (error instanceof TimesheetRuleError || error instanceof TimesheetConflictError) {
        closeSubmitConfirm();
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  async function handleApprove() {
    setRuleError(null);
    try {
      await approveWeek.mutateAsync();
      notifications.show({ title: "Timesheet approved", message: "" });
    } catch (error) {
      if (error instanceof TimesheetRuleError || error instanceof TimesheetConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  async function handleReturn() {
    setRuleError(null);
    try {
      await returnWeek.mutateAsync(returnComment);
      setReturnComment("");
      closeReturn();
      notifications.show({ title: "Timesheet returned", message: "" });
    } catch (error) {
      if (error instanceof TimesheetRuleError || error instanceof TimesheetConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
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
      <Group justify="space-between" align="flex-start" mb="sm" wrap="wrap">
        <Group gap="xs">
          <Badge color={STATUS_COLOR[week.status]}>{STATUS_LABEL[week.status]}</Badge>
          {week.status !== "draft" && week.submitted_at && (
            <Text size="sm" c="dimmed">
              Submitted {new Date(week.submitted_at).toLocaleString()}
            </Text>
          )}
          {(week.status === "approved" || week.status === "returned") &&
            week.reviewed_at &&
            week.reviewed_by_name && (
              <Text size="sm" c="dimmed">
                {week.status === "approved" ? "Approved" : "Returned"} by {week.reviewed_by_name} ·{" "}
                {new Date(week.reviewed_at).toLocaleString()}
              </Text>
            )}
        </Group>
        {week.can_review && (
          <Group gap="xs">
            {week.status === "submitted" && (
              <Button size="xs" loading={approveWeek.isPending} onClick={() => void handleApprove()}>
                Approve
              </Button>
            )}
            <Button size="xs" variant="default" onClick={openReturn}>
              Return…
            </Button>
          </Group>
        )}
      </Group>

      {week.status === "returned" && week.return_comment && (
        <Alert color="orange" mb="sm" title="Returned for corrections">
          {week.return_comment}
        </Alert>
      )}

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
                comment={rowComment(row)}
                onCommentChange={(comment) => setRowComment(row, comment)}
                onDelete={() => handleDeleteRow(row)}
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
            <Button
              variant="default"
              disabled={!isDirty && !hasPendingPrefill}
              loading={saveWeek.isPending}
              onClick={() => void handleSave()}
            >
              Save
            </Button>
            {week.can_submit && (
              <Button loading={submitWeek.isPending} onClick={openSubmitConfirm}>
                Submit
              </Button>
            )}
          </Group>
        </Group>
      )}

      <AddRowModal
        opened={addRowOpened}
        onClose={closeAddRow}
        excludeBillingItemIds={excludeIds}
        onAdd={(picked) => setAddedRows((previous) => [...previous, picked])}
      />

      <Modal opened={submitConfirmOpened} onClose={closeSubmitConfirm} title="Submit this week?">
        <Stack>
          <Text>
            After submitting, you won't be able to edit this week until a manager returns it to
            you for corrections.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeSubmitConfirm}>
              Cancel
            </Button>
            <Button loading={saveWeek.isPending || submitWeek.isPending} onClick={() => void handleConfirmSubmit()}>
              Submit
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={returnOpened} onClose={closeReturn} title="Return this week for corrections">
        <Stack>
          <Textarea
            label="Comment"
            description="Tell the worker what needs to change"
            required
            autosize
            minRows={3}
            value={returnComment}
            onChange={(event) => setReturnComment(event.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={closeReturn}>
              Cancel
            </Button>
            <Button
              color="orange"
              disabled={returnComment.trim() === ""}
              loading={returnWeek.isPending}
              onClick={() => void handleReturn()}
            >
              Return
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function DayHeader({ day }: { day: CalendarDay }) {
  const kind = dayKind(day);
  const background = dayKindBackground(kind);
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
  comment,
  onCommentChange,
  onDelete,
}: {
  row: TimesheetRow;
  days: CalendarDay[];
  canEdit: boolean;
  cellValue: (row: TimesheetRow, date: string) => CellDraft;
  setCell: (row: TimesheetRow, date: string, patch: Partial<CellDraft>) => void;
  comment: string | null;
  onCommentChange: (comment: string) => void;
  onDelete: () => void;
}) {
  const [commentOpened, { open: openComment, close: closeComment }] = useDisclosure(false);
  const total = days.reduce((sum, day) => sum + (cellValue(row, day.day).quantity ?? 0), 0);
  return (
    <Table.Tr>
      <Table.Td>
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <div>
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
          </div>
          <Group gap={2} wrap="nowrap">
            <Popover opened={commentOpened} onClose={closeComment} withArrow>
              <Popover.Target>
                <Tooltip label={comment ?? "Add a comment"} disabled={!comment}>
                  <ActionIcon
                    variant={comment ? "light" : "subtle"}
                    color="gray"
                    size="sm"
                    aria-label={`Comment for ${row.billing_item.name}`}
                    onClick={commentOpened ? closeComment : openComment}
                  >
                    💬
                  </ActionIcon>
                </Tooltip>
              </Popover.Target>
              <Popover.Dropdown>
                {canEdit ? (
                  <Textarea
                    aria-label={`Comment text for ${row.billing_item.name}`}
                    placeholder="Comment"
                    autosize
                    minRows={2}
                    w={220}
                    value={comment ?? ""}
                    onChange={(event) => onCommentChange(event.currentTarget.value)}
                  />
                ) : (
                  <Text size="sm" w={220}>
                    {comment ?? "No comment"}
                  </Text>
                )}
              </Popover.Dropdown>
            </Popover>
            {canEdit && (
              <ActionIcon
                variant="subtle"
                color="red"
                size="sm"
                aria-label={`Delete row ${row.billing_item.name}`}
                onClick={onDelete}
              >
                🗑
              </ActionIcon>
            )}
          </Group>
        </Group>
      </Table.Td>
      {days.map((day) => (
        <Table.Td key={day.day} data-kind={dayKind(day)}>
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
