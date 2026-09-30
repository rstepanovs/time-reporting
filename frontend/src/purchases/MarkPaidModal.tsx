import { Alert, Button, Group, Modal, NumberInput, Select, Stack, Text } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { todayIso } from "@/timesheets/week";
import {
  PurchaseConflictError,
  PurchaseRuleError,
  type PaymentMethod,
  type PurchaseDocument,
} from "@/purchases/api";
import { KIND_LABEL, METHOD_LABEL } from "@/purchases/format";
import { useMarkPurchasePaid } from "@/purchases/hooks";

/** "Paid…": the payment date, the method and, optionally, the base-currency amount the bank
 * actually debited (otherwise it is converted at the rate of the payment date). */
export function MarkPaidModal({
  document,
  baseCurrency,
  onClose,
}: {
  document: PurchaseDocument | null;
  baseCurrency: string;
  onClose: () => void;
}) {
  const markPaid = useMarkPurchasePaid();
  const [paidOn, setPaidOn] = useState(todayIso());
  const [method, setMethod] = useState<PaymentMethod | null>(null);
  const [amountBase, setAmountBase] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isCardInvoice = document?.kind === "card_invoice";
  const methods = (Object.keys(METHOD_LABEL) as PaymentMethod[])
    .filter((value) => !(isCardInvoice && value === "card"))
    .map((value) => ({ value, label: METHOD_LABEL[value] }));
  const foreign = document?.currency !== undefined && document.currency !== baseCurrency;

  async function handleSubmit() {
    if (!document || !method) return;
    setError(null);
    try {
      await markPaid.mutateAsync({
        documentId: document.id,
        paidOn,
        paymentMethod: method,
        amountBase: amountBase || null,
      });
      notifications.show({ title: "Marked paid", message: document.vendor ?? document.file_name });
      onClose();
    } catch (payError) {
      if (payError instanceof PurchaseConflictError || payError instanceof PurchaseRuleError) {
        setError(payError.message);
        return;
      }
      throw payError;
    }
  }

  return (
    <Modal opened={document !== null} onClose={onClose} title="Mark as paid">
      {document && (
        <Stack>
          <Text size="sm" c="dimmed">
            {KIND_LABEL[document.kind ?? "other"]} {document.document_no} · {document.vendor}
          </Text>
          {error && <Alert color="red">{error}</Alert>}
          <DateInput
            label="Paid on"
            required
            value={paidOn}
            onChange={(value) => setPaidOn(value ?? "")}
          />
          <Select
            label="Payment method"
            required
            data={methods}
            value={method}
            onChange={(value) => setMethod(value as PaymentMethod | null)}
          />
          {foreign && (
            <NumberInput
              label={`${baseCurrency} amount debited (optional)`}
              description={`Leave empty to convert at the rate of the payment date.`}
              decimalScale={2}
              min={0}
              value={amountBase === "" ? "" : Number(amountBase)}
              onChange={(value) => setAmountBase(value === "" ? "" : String(value))}
            />
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button
              loading={markPaid.isPending}
              disabled={!paidOn || !method}
              onClick={() => void handleSubmit()}
            >
              Mark paid
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
