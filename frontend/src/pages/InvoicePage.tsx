import { Alert, Anchor, Badge, Button, Group, Loader, Modal, Stack, Text, Textarea, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  InvoiceConflictError,
  InvoiceRuleError,
  invoicePdfUrl,
  type InvoiceStatus,
} from "@/invoices/api";
import {
  useDeleteInvoiceDraft,
  useInvoice,
  useMarkInvoicePaid,
  useVoidInvoice,
} from "@/invoices/hooks";
import { InvoiceLinesTable } from "@/invoices/InvoiceLinesTable";
import { todayIso } from "@/timesheets/week";

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

export function InvoicePage() {
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const navigate = useNavigate();
  const invoiceQuery = useInvoice(invoiceId ?? "");
  const deleteDraft = useDeleteInvoiceDraft();
  const markPaid = useMarkInvoicePaid(invoiceId ?? "");
  const voidInvoice = useVoidInvoice(invoiceId ?? "");

  const [isDirty, setIsDirty] = useState(false);
  const [confirmLeaveOpened, { open: openConfirmLeave, close: closeConfirmLeave }] =
    useDisclosure(false);
  const [deleteOpened, { open: openDelete, close: closeDelete }] = useDisclosure(false);
  const [payOpened, { open: openPay, close: closePay }] = useDisclosure(false);
  const [voidOpened, { open: openVoid, close: closeVoid }] = useDisclosure(false);
  const [paidOn, setPaidOn] = useState<string>(todayIso());
  const [voidReason, setVoidReason] = useState("");
  const [ruleError, setRuleError] = useState<string | null>(null);

  function backToList() {
    if (isDirty) {
      openConfirmLeave();
      return;
    }
    navigate("/invoices");
  }

  if (invoiceQuery.isPending) return <Loader />;

  if (invoiceQuery.isError) {
    if (invoiceQuery.error instanceof InvoiceRuleError) {
      return (
        <Stack>
          <Title order={2}>Invoice not found</Title>
          <Anchor component={Link} to="/invoices">
            Back to invoices
          </Anchor>
        </Stack>
      );
    }
    return <Alert color="red">Could not load the invoice.</Alert>;
  }

  const invoice = invoiceQuery.data;
  const overdue = invoice.status === "issued" && invoice.due_date < todayIso();

  async function handleDelete() {
    await deleteDraft.mutateAsync(invoice.id);
    closeDelete();
    notifications.show({ title: "Draft deleted", message: "" });
    navigate("/invoices");
  }

  async function handleMarkPaid() {
    setRuleError(null);
    try {
      await markPaid.mutateAsync(paidOn);
      closePay();
      notifications.show({ title: "Invoice marked paid", message: "" });
    } catch (error) {
      if (error instanceof InvoiceRuleError || error instanceof InvoiceConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  async function handleVoid() {
    setRuleError(null);
    try {
      await voidInvoice.mutateAsync(voidReason);
      setVoidReason("");
      closeVoid();
      notifications.show({ title: "Invoice voided", message: "" });
    } catch (error) {
      if (error instanceof InvoiceRuleError || error instanceof InvoiceConflictError) {
        setRuleError(error.message);
        return;
      }
      throw error;
    }
  }

  return (
    <Stack>
      <Anchor
        component="button"
        type="button"
        onClick={backToList}
        style={{ alignSelf: "flex-start" }}
      >
        ← Back to invoices
      </Anchor>

      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Group gap="sm">
            <Title order={2}>{invoice.number ?? "Draft invoice"}</Title>
            <Badge color={overdue ? "red" : STATUS_COLOR[invoice.status]}>
              {overdue ? "Overdue" : STATUS_LABEL[invoice.status]}
            </Badge>
          </Group>
          <Text c="dimmed">
            {invoice.customer.name} · {invoice.currency}
          </Text>
          {invoice.status !== "draft" && (
            <Text size="sm" c="dimmed">
              {invoice.invoice_date} · due {invoice.due_date}
              {invoice.your_reference && ` · Ref: ${invoice.your_reference}`}
            </Text>
          )}
          {invoice.issued_at && (
            <Text size="sm" c="dimmed">
              Issued {new Date(invoice.issued_at).toLocaleString()}
            </Text>
          )}
          {invoice.paid_on && (
            <Text size="sm" c="dimmed">
              Paid on {invoice.paid_on}
            </Text>
          )}
          {invoice.voided_at && (
            <Text size="sm" c="dimmed">
              Voided {new Date(invoice.voided_at).toLocaleString()}
            </Text>
          )}
        </div>
        <Group>
          {invoice.status === "draft" ? (
            <Anchor href={invoicePdfUrl(invoice.id)} target="_blank" rel="noopener noreferrer">
              Preview PDF
            </Anchor>
          ) : (
            <Anchor href={invoicePdfUrl(invoice.id)} download>
              Download PDF
            </Anchor>
          )}
          {invoice.status === "draft" && (
            <Button size="xs" variant="default" color="red" onClick={openDelete}>
              Delete draft
            </Button>
          )}
          {invoice.status === "issued" && (
            <Button size="xs" variant="default" onClick={openPay}>
              Mark paid…
            </Button>
          )}
          {(invoice.status === "issued" || invoice.status === "paid") && (
            <Button size="xs" variant="default" color="red" onClick={openVoid}>
              Void…
            </Button>
          )}
        </Group>
      </Group>

      {invoice.status === "void" && invoice.void_reason && (
        <Alert color="red" title="Voided">
          {invoice.void_reason}
        </Alert>
      )}
      {invoice.notes && invoice.status !== "draft" && (
        <Alert color="gray" variant="light" title="Notes">
          {invoice.notes}
        </Alert>
      )}

      {ruleError && (
        <Alert color="red" onClose={() => setRuleError(null)} withCloseButton>
          {ruleError}
        </Alert>
      )}

      <InvoiceLinesTable invoice={invoice} onDirtyChange={setIsDirty} />

      <Modal opened={confirmLeaveOpened} onClose={closeConfirmLeave} title="Discard unsaved changes?">
        <Stack>
          <Text>You have unsaved changes on this invoice. Leaving now will discard them.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeConfirmLeave}>
              Cancel
            </Button>
            <Button
              color="red"
              onClick={() => {
                closeConfirmLeave();
                navigate("/invoices");
              }}
            >
              Discard and continue
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={deleteOpened} onClose={closeDelete} title="Delete this draft?">
        <Stack>
          <Text>This cannot be undone, and frees every billing period it covered.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={closeDelete}>
              Cancel
            </Button>
            <Button color="red" loading={deleteDraft.isPending} onClick={() => void handleDelete()}>
              Delete
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={payOpened} onClose={closePay} title="Mark this invoice paid">
        <Stack>
          <DateInput
            label="Paid on"
            required
            value={paidOn}
            onChange={(value) => setPaidOn(value ?? "")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={closePay}>
              Cancel
            </Button>
            <Button
              loading={markPaid.isPending}
              disabled={!paidOn}
              onClick={() => void handleMarkPaid()}
            >
              Mark paid
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={voidOpened} onClose={closeVoid} title="Void this invoice">
        <Stack>
          <Text size="sm" c="dimmed">
            The number and PDF are kept as a record; every billing period it covered becomes
            invoiceable again.
          </Text>
          <Textarea
            label="Reason"
            required
            autosize
            minRows={2}
            value={voidReason}
            onChange={(event) => setVoidReason(event.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={closeVoid}>
              Cancel
            </Button>
            <Button
              color="red"
              disabled={voidReason.trim() === ""}
              loading={voidInvoice.isPending}
              onClick={() => void handleVoid()}
            >
              Void
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
