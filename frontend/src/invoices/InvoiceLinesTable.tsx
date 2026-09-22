import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import {
  InvoiceConflictError,
  InvoiceRuleError,
  type ClearableInvoiceField,
  type Invoice,
  type InvoiceLine,
  type InvoiceLineChange,
} from "@/invoices/api";
import { useIssueInvoice, useUpdateInvoiceDraft } from "@/invoices/hooks";

/** A line's editable fields as plain strings — parsed only when building the save request, so a
 * half-typed quantity/price never gets silently coerced mid-edit. `amount` is never part of
 * this — the service always recomputes it as `quantity * unit_price`. */
type LineFields = { description: string; quantity: string; unit: string; unitPrice: string };
type NewLine = { tempId: string; fields: LineFields };
type HeaderFields = { invoiceDate: string; dueDate: string; yourReference: string; notes: string };

let nextTempId = 0;

function emptyLineFields(): LineFields {
  return { description: "", quantity: "", unit: "", unitPrice: "" };
}

function toLineFields(line: InvoiceLine): LineFields {
  return {
    description: line.description,
    quantity: line.quantity,
    unit: line.unit,
    unitPrice: line.unit_price,
  };
}

function isLineComplete(fields: LineFields): boolean {
  return (
    fields.description.trim() !== "" &&
    fields.unit.trim() !== "" &&
    fields.quantity !== "" &&
    Number(fields.quantity) > 0 &&
    fields.unitPrice !== "" &&
    Number(fields.unitPrice) >= 0
  );
}

function toLineChange(fields: LineFields, lineId: string | null): InvoiceLineChange {
  return {
    line_id: lineId,
    description: fields.description.trim(),
    quantity: fields.quantity,
    unit: fields.unit.trim(),
    unit_price: fields.unitPrice,
  };
}

function toHeaderFields(invoice: Invoice): HeaderFields {
  return {
    invoiceDate: invoice.invoice_date,
    dueDate: invoice.due_date,
    yourReference: invoice.your_reference ?? "",
    notes: invoice.notes ?? "",
  };
}

type Props = {
  invoice: Invoice;
  onDirtyChange: (dirty: boolean) => void;
};

/** The draft's editable header (dates, reference, notes) and its lines, with a local draft, an
 * explicit Save/Discard and an "Issue…" action that auto-saves first — the `ExpenseLinesTable`
 * pattern (one combined `UpdateInvoiceDraft` call per Save, matching the backend's own shape).
 * Once the invoice leaves `draft`, renders the same lines read-only with no header fields (the
 * page's own header already shows them as plain text) and no actions. */
export function InvoiceLinesTable({ invoice, onDirtyChange }: Props) {
  const canEdit = invoice.status === "draft";
  const updateDraft = useUpdateInvoiceDraft(invoice.id);
  const issueInvoice = useIssueInvoice(invoice.id);

  const [headerEdits, setHeaderEdits] = useState<Partial<HeaderFields>>({});
  const [edits, setEdits] = useState<Map<string, LineFields>>(new Map());
  const [deletedLineIds, setDeletedLineIds] = useState<Set<string>>(new Set());
  const [newLines, setNewLines] = useState<NewLine[]>([]);
  const [ruleError, setRuleError] = useState<string | null>(null);
  const [issueOpened, { open: openIssue, close: closeIssue }] = useDisclosure(false);

  const header: HeaderFields = { ...toHeaderFields(invoice), ...headerEdits };

  const isDirty =
    canEdit &&
    (Object.keys(headerEdits).length > 0 ||
      edits.size > 0 ||
      deletedLineIds.size > 0 ||
      newLines.length > 0);

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  const visibleLines = invoice.lines.filter((line) => !deletedLineIds.has(line.id));
  const hasAnyLine = visibleLines.length > 0 || newLines.length > 0;

  function fieldsFor(line: InvoiceLine): LineFields {
    return edits.get(line.id) ?? toLineFields(line);
  }

  function setHeaderField(key: keyof HeaderFields, value: string) {
    setHeaderEdits((previous) => ({ ...previous, [key]: value }));
  }

  function setFields(lineId: string, patch: Partial<LineFields>) {
    setEdits((previous) => {
      const next = new Map(previous);
      const current =
        previous.get(lineId) ?? toLineFields(invoice.lines.find((line) => line.id === lineId)!);
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
    setNewLines((previous) => [
      ...previous,
      { tempId: `new-${(nextTempId += 1)}`, fields: emptyLineFields() },
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
    setHeaderEdits({});
    setEdits(new Map());
    setDeletedLineIds(new Set());
    setNewLines([]);
  }

  async function persistDraft(): Promise<void> {
    const lines: InvoiceLineChange[] = [];
    for (const [lineId, fields] of edits.entries()) lines.push(toLineChange(fields, lineId));
    for (const entry of newLines) lines.push(toLineChange(entry.fields, null));

    const clearFields: ClearableInvoiceField[] = [];
    if (header.yourReference.trim() === "") clearFields.push("your_reference");
    if (header.notes.trim() === "") clearFields.push("notes");

    await updateDraft.mutateAsync({
      invoiceDate: header.invoiceDate,
      dueDate: header.dueDate,
      yourReference: header.yourReference.trim() || undefined,
      notes: header.notes.trim() || undefined,
      lines,
      deleteLineIds: Array.from(deletedLineIds),
      clearFields,
    });
    resetDraft();
  }

  async function handleSave() {
    setRuleError(null);
    try {
      await persistDraft();
      notifications.show({ title: "Invoice saved", message: "" });
    } catch (error) {
      if (error instanceof InvoiceRuleError || error instanceof InvoiceConflictError) {
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

  async function handleConfirmIssue() {
    setRuleError(null);
    try {
      if (isDirty) await persistDraft();
      await issueInvoice.mutateAsync();
      closeIssue();
      notifications.show({ title: "Invoice issued", message: "" });
    } catch (error) {
      if (error instanceof InvoiceRuleError || error instanceof InvoiceConflictError) {
        closeIssue();
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  const allComplete =
    Array.from(edits.values()).every(isLineComplete) &&
    newLines.every((entry) => isLineComplete(entry.fields));

  return (
    <Stack>
      {ruleError && (
        <Alert color="red" onClose={() => setRuleError(null)} withCloseButton>
          {ruleError}
        </Alert>
      )}

      {canEdit && (
        <>
          <Group align="flex-end" wrap="wrap">
            <DateInput
              label="Invoice date"
              required
              value={header.invoiceDate}
              onChange={(value) => setHeaderField("invoiceDate", value ?? "")}
              w={160}
            />
            <DateInput
              label="Due date"
              required
              value={header.dueDate}
              onChange={(value) => setHeaderField("dueDate", value ?? "")}
              w={160}
            />
            <TextInput
              label="Your reference"
              value={header.yourReference}
              onChange={(event) => setHeaderField("yourReference", event.currentTarget.value)}
              maxLength={255}
              w={220}
            />
          </Group>
          <Textarea
            label="Notes"
            autosize
            minRows={2}
            value={header.notes}
            onChange={(event) => setHeaderField("notes", event.currentTarget.value)}
          />
        </>
      )}

      <Table.ScrollContainer minWidth={720}>
        <Table withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Description</Table.Th>
              <Table.Th>Quantity</Table.Th>
              <Table.Th>Unit</Table.Th>
              <Table.Th>Unit price</Table.Th>
              <Table.Th>Amount</Table.Th>
              {canEdit && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {visibleLines.map((line) => {
              const fields = fieldsFor(line);
              return (
                <Table.Tr key={line.id}>
                  {canEdit ? (
                    <EditableCells fields={fields} onChange={(patch) => setFields(line.id, patch)} />
                  ) : (
                    <ReadOnlyCells fields={fields} amount={line.amount} />
                  )}
                  {canEdit && (
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
            {!hasAnyLine && (
              <Table.Tr>
                <Table.Td colSpan={canEdit ? 6 : 5}>
                  <Text c="dimmed">No lines yet.</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th colSpan={4}>Subtotal</Table.Th>
              <Table.Th>
                {invoice.subtotal} {invoice.currency}
              </Table.Th>
              {canEdit && <Table.Th />}
            </Table.Tr>
            {invoice.vat_rate !== null && (
              <Table.Tr>
                <Table.Th colSpan={4}>VAT ({invoice.vat_rate}%)</Table.Th>
                <Table.Th>
                  {invoice.vat_amount} {invoice.currency}
                </Table.Th>
                {canEdit && <Table.Th />}
              </Table.Tr>
            )}
            <Table.Tr>
              <Table.Th colSpan={4}>Total</Table.Th>
              <Table.Th>
                {invoice.total} {invoice.currency}
              </Table.Th>
              {canEdit && <Table.Th />}
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      </Table.ScrollContainer>

      {canEdit && (
        <Group justify="space-between">
          <Button variant="default" onClick={handleAddLine}>
            Add line
          </Button>
          <Group>
            <Button variant="default" disabled={!isDirty} onClick={handleDiscard}>
              Discard
            </Button>
            <Button
              variant="default"
              disabled={!isDirty || !allComplete}
              loading={updateDraft.isPending}
              onClick={() => void handleSave()}
            >
              Save
            </Button>
            <Button
              onClick={openIssue}
              disabled={(isDirty && !allComplete) || !hasAnyLine}
              loading={issueInvoice.isPending}
            >
              Issue…
            </Button>
          </Group>
        </Group>
      )}

      <Modal opened={issueOpened} onClose={closeIssue} title="Issue this invoice?">
        <Stack>
          <Text>
            Issuing saves any unsaved changes, allocates its number, renders the PDF and makes the
            invoice permanent — it can no longer be edited or deleted afterwards.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeIssue}>
              Cancel
            </Button>
            <Button
              loading={updateDraft.isPending || issueInvoice.isPending}
              onClick={() => void handleConfirmIssue()}
            >
              Issue
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function EditableCells({
  fields,
  onChange,
}: {
  fields: LineFields;
  onChange: (patch: Partial<LineFields>) => void;
}) {
  const amount =
    fields.quantity !== "" && fields.unitPrice !== ""
      ? (Number(fields.quantity) * Number(fields.unitPrice)).toFixed(2)
      : "";
  return (
    <>
      <Table.Td>
        <TextInput
          aria-label="Description"
          value={fields.description}
          onChange={(event) => onChange({ description: event.currentTarget.value })}
          maxLength={500}
          w={220}
        />
      </Table.Td>
      <Table.Td>
        <NumberInput
          aria-label="Quantity"
          value={fields.quantity === "" ? "" : Number(fields.quantity)}
          onChange={(value) => onChange({ quantity: value === "" ? "" : String(value) })}
          min={0.01}
          decimalScale={2}
          hideControls
          w={100}
        />
      </Table.Td>
      <Table.Td>
        <TextInput
          aria-label="Unit"
          value={fields.unit}
          onChange={(event) => onChange({ unit: event.currentTarget.value })}
          maxLength={20}
          w={90}
        />
      </Table.Td>
      <Table.Td>
        <NumberInput
          aria-label="Unit price"
          value={fields.unitPrice === "" ? "" : Number(fields.unitPrice)}
          onChange={(value) => onChange({ unitPrice: value === "" ? "" : String(value) })}
          min={0}
          decimalScale={2}
          hideControls
          w={110}
        />
      </Table.Td>
      <Table.Td>{amount}</Table.Td>
    </>
  );
}

function ReadOnlyCells({ fields, amount }: { fields: LineFields; amount: string }) {
  return (
    <>
      <Table.Td>{fields.description}</Table.Td>
      <Table.Td>{fields.quantity}</Table.Td>
      <Table.Td>{fields.unit}</Table.Td>
      <Table.Td>{fields.unitPrice}</Table.Td>
      <Table.Td>{amount}</Table.Td>
    </>
  );
}
