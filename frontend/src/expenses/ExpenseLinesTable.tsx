import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import {
  ExpenseConflictError,
  ExpenseRuleError,
  type ExpenseBillingItem,
  type ExpenseLine,
  type ExpenseLineChange,
  type ExpenseReport,
} from "@/expenses/api";
import { useSaveExpenseReportLines, useSubmitExpenseReport } from "@/expenses/hooks";

/** An existing or not-yet-saved line's editable fields, as plain strings — parsed only when
 * building the save request, so a half-typed amount never gets silently coerced mid-edit. */
type LineFields = {
  billingItemId: string;
  expenseDate: string;
  amount: string;
  description: string;
  vendor: string;
  documentNo: string;
};

type NewLine = { tempId: string; fields: LineFields };

let nextTempId = 0;

function emptyFields(defaultBillingItemId: string, defaultDate: string): LineFields {
  return {
    billingItemId: defaultBillingItemId,
    expenseDate: defaultDate,
    amount: "",
    description: "",
    vendor: "",
    documentNo: "",
  };
}

function toFields(line: ExpenseLine): LineFields {
  return {
    billingItemId: line.billing_item.id,
    expenseDate: line.expense_date,
    amount: line.amount,
    description: line.description,
    vendor: line.vendor ?? "",
    documentNo: line.document_no ?? "",
  };
}

function isComplete(fields: LineFields): boolean {
  return (
    fields.billingItemId !== "" &&
    fields.expenseDate !== "" &&
    fields.amount !== "" &&
    Number(fields.amount) > 0 &&
    fields.description.trim() !== ""
  );
}

function toChange(fields: LineFields, lineId: string | null): ExpenseLineChange {
  return {
    line_id: lineId,
    billing_item_id: fields.billingItemId,
    expense_date: fields.expenseDate,
    amount: fields.amount,
    description: fields.description.trim(),
    vendor: fields.vendor.trim() || null,
    document_no: fields.documentNo.trim() || null,
  };
}

type Props = {
  report: ExpenseReport;
  billingItems: ExpenseBillingItem[];
  onDirtyChange: (dirty: boolean) => void;
};

export function ExpenseLinesTable({ report, billingItems, onDirtyChange }: Props) {
  const saveLines = useSaveExpenseReportLines(report.id);
  const submitReport = useSubmitExpenseReport(report.id);

  const [edits, setEdits] = useState<Map<string, LineFields>>(new Map());
  const [deletedLineIds, setDeletedLineIds] = useState<Set<string>>(new Set());
  const [newLines, setNewLines] = useState<NewLine[]>([]);
  const [ruleError, setRuleError] = useState<string | null>(null);
  const [submitConfirmOpened, { open: openSubmitConfirm, close: closeSubmitConfirm }] =
    useDisclosure(false);

  const isDirty = edits.size > 0 || deletedLineIds.size > 0 || newLines.length > 0;
  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  const visibleLines = report.lines.filter((line) => !deletedLineIds.has(line.id));

  // The item currently on an existing line is always selectable, even if it has since been
  // archived — otherwise editing any other field of that line would silently drop it.
  const itemOptions = new Map(billingItems.map((item) => [item.id, item]));
  for (const line of report.lines) {
    if (!itemOptions.has(line.billing_item.id)) itemOptions.set(line.billing_item.id, line.billing_item);
  }
  const selectData = Array.from(itemOptions.values()).map((item) => ({
    value: item.id,
    label: item.name,
  }));

  function fieldsFor(line: ExpenseLine): LineFields {
    return edits.get(line.id) ?? toFields(line);
  }

  function setFields(lineId: string, patch: Partial<LineFields>) {
    setEdits((previous) => {
      const next = new Map(previous);
      const current = previous.get(lineId) ?? toFields(report.lines.find((l) => l.id === lineId)!);
      next.set(lineId, { ...current, ...patch });
      return next;
    });
  }

  function setNewLineFields(tempId: string, patch: Partial<LineFields>) {
    setNewLines((previous) =>
      previous.map((entry) =>
        entry.tempId === tempId ? { ...entry, fields: { ...entry.fields, ...patch } } : entry,
      ),
    );
  }

  function handleAddLine() {
    const defaultItem = selectData[0]?.value ?? "";
    setNewLines((previous) => [
      ...previous,
      { tempId: `new-${(nextTempId += 1)}`, fields: emptyFields(defaultItem, report.period_start) },
    ]);
  }

  function handleDeleteExistingLine(lineId: string) {
    setDeletedLineIds((previous) => new Set(previous).add(lineId));
    setEdits((previous) => {
      const next = new Map(previous);
      next.delete(lineId);
      return next;
    });
  }

  function handleDeleteNewLine(tempId: string) {
    setNewLines((previous) => previous.filter((entry) => entry.tempId !== tempId));
  }

  function resetDraft() {
    setEdits(new Map());
    setDeletedLineIds(new Set());
    setNewLines([]);
  }

  async function persistDraft(): Promise<void> {
    const lines: ExpenseLineChange[] = [];
    for (const [lineId, fields] of edits.entries()) {
      lines.push(toChange(fields, lineId));
    }
    for (const entry of newLines) {
      lines.push(toChange(entry.fields, null));
    }
    await saveLines.mutateAsync({ lines, deleteLineIds: Array.from(deletedLineIds) });
    resetDraft();
  }

  async function handleSave() {
    setRuleError(null);
    try {
      await persistDraft();
      notifications.show({ title: "Expense report saved", message: "" });
    } catch (error) {
      if (error instanceof ExpenseRuleError || error instanceof ExpenseConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  function handleDiscard() {
    resetDraft();
    setRuleError(null);
  }

  async function handleConfirmSubmit() {
    setRuleError(null);
    try {
      if (isDirty) await persistDraft();
      await submitReport.mutateAsync();
      closeSubmitConfirm();
      notifications.show({ title: "Expense report submitted", message: "" });
    } catch (error) {
      if (error instanceof ExpenseRuleError || error instanceof ExpenseConflictError) {
        closeSubmitConfirm();
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  const allComplete =
    Array.from(edits.values()).every(isComplete) && newLines.every((entry) => isComplete(entry.fields));

  const total = visibleLines
    .map((line) => Number(fieldsFor(line).amount || 0))
    .concat(newLines.map((entry) => Number(entry.fields.amount || 0)))
    .reduce((sum, value) => sum + value, 0);

  return (
    <Stack>
      {ruleError && (
        <Alert color="red" onClose={() => setRuleError(null)} withCloseButton>
          {ruleError}
        </Alert>
      )}

      <Table.ScrollContainer minWidth={720}>
        <Table withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Date</Table.Th>
              <Table.Th>Billing item</Table.Th>
              <Table.Th>Amount</Table.Th>
              <Table.Th>Description</Table.Th>
              <Table.Th>Vendor</Table.Th>
              <Table.Th>Document no.</Table.Th>
              {report.can_edit && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {visibleLines.map((line) => {
              const fields = fieldsFor(line);
              return (
                <Table.Tr key={line.id}>
                  {report.can_edit ? (
                    <EditableCells
                      fields={fields}
                      periodStart={report.period_start}
                      periodEnd={report.period_end}
                      selectData={selectData}
                      onChange={(patch) => setFields(line.id, patch)}
                    />
                  ) : (
                    <ReadOnlyCells fields={fields} itemName={line.billing_item.name} />
                  )}
                  {report.can_edit && (
                    <Table.Td>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        aria-label={`Delete line ${fields.description}`}
                        onClick={() => handleDeleteExistingLine(line.id)}
                      >
                        🗑
                      </ActionIcon>
                    </Table.Td>
                  )}
                </Table.Tr>
              );
            })}
            {newLines.map((entry) => (
              <Table.Tr key={entry.tempId}>
                <EditableCells
                  fields={entry.fields}
                  periodStart={report.period_start}
                  periodEnd={report.period_end}
                  selectData={selectData}
                  onChange={(patch) => setNewLineFields(entry.tempId, patch)}
                />
                <Table.Td>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    aria-label="Delete new line"
                    onClick={() => handleDeleteNewLine(entry.tempId)}
                  >
                    🗑
                  </ActionIcon>
                </Table.Td>
              </Table.Tr>
            ))}
            {visibleLines.length === 0 && newLines.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={report.can_edit ? 7 : 6}>
                  <Text c="dimmed">No lines yet.</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th colSpan={2}>Total</Table.Th>
              <Table.Th>{total > 0 ? `${total.toFixed(2)} ${report.project.customer.currency}` : ""}</Table.Th>
              <Table.Th colSpan={report.can_edit ? 4 : 3} />
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      </Table.ScrollContainer>

      {report.can_edit && (
        <Group justify="space-between">
          <Button variant="default" onClick={handleAddLine} disabled={selectData.length === 0}>
            Add line
          </Button>
          <Group>
            <Button variant="default" disabled={!isDirty} onClick={handleDiscard}>
              Discard
            </Button>
            <Button
              variant="default"
              disabled={!isDirty || !allComplete}
              loading={saveLines.isPending}
              onClick={() => void handleSave()}
            >
              Save
            </Button>
            {report.can_submit && (
              <Button
                loading={submitReport.isPending}
                onClick={openSubmitConfirm}
                disabled={isDirty && !allComplete}
              >
                Submit
              </Button>
            )}
          </Group>
        </Group>
      )}

      <Modal opened={submitConfirmOpened} onClose={closeSubmitConfirm} title="Submit this report?">
        <Stack>
          <Text>
            After submitting, you won't be able to edit this report until a manager returns it to
            you for corrections.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeSubmitConfirm}>
              Cancel
            </Button>
            <Button
              loading={saveLines.isPending || submitReport.isPending}
              onClick={() => void handleConfirmSubmit()}
            >
              Submit
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function EditableCells({
  fields,
  periodStart,
  periodEnd,
  selectData,
  onChange,
}: {
  fields: LineFields;
  periodStart: string;
  periodEnd: string;
  selectData: { value: string; label: string }[];
  onChange: (patch: Partial<LineFields>) => void;
}) {
  return (
    <>
      <Table.Td>
        <DateInput
          aria-label="Expense date"
          value={fields.expenseDate}
          onChange={(value) => onChange({ expenseDate: value ?? "" })}
          minDate={periodStart}
          maxDate={periodEnd}
          w={140}
        />
      </Table.Td>
      <Table.Td>
        <Select
          aria-label="Billing item"
          data={selectData}
          value={fields.billingItemId}
          onChange={(value) => onChange({ billingItemId: value ?? "" })}
          allowDeselect={false}
          w={180}
        />
      </Table.Td>
      <Table.Td>
        <NumberInput
          aria-label="Amount"
          value={fields.amount === "" ? "" : Number(fields.amount)}
          onChange={(value) => onChange({ amount: value === "" ? "" : String(value) })}
          min={0.01}
          decimalScale={2}
          hideControls
          w={110}
        />
      </Table.Td>
      <Table.Td>
        <TextInput
          aria-label="Description"
          value={fields.description}
          onChange={(event) => onChange({ description: event.currentTarget.value })}
          maxLength={255}
          w={200}
        />
      </Table.Td>
      <Table.Td>
        <TextInput
          aria-label="Vendor"
          value={fields.vendor}
          onChange={(event) => onChange({ vendor: event.currentTarget.value })}
          maxLength={255}
          w={160}
        />
      </Table.Td>
      <Table.Td>
        <TextInput
          aria-label="Document no."
          value={fields.documentNo}
          onChange={(event) => onChange({ documentNo: event.currentTarget.value })}
          maxLength={100}
          w={140}
        />
      </Table.Td>
    </>
  );
}

function ReadOnlyCells({ fields, itemName }: { fields: LineFields; itemName: string }) {
  return (
    <>
      <Table.Td>{fields.expenseDate}</Table.Td>
      <Table.Td>{itemName}</Table.Td>
      <Table.Td>{fields.amount}</Table.Td>
      <Table.Td>{fields.description}</Table.Td>
      <Table.Td>{fields.vendor}</Table.Td>
      <Table.Td>{fields.documentNo}</Table.Td>
    </>
  );
}
