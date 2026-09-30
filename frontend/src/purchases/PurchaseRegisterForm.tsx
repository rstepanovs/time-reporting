import {
  Alert,
  Button,
  Group,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  PurchaseConflictError,
  PurchaseRuleError,
  type PaymentMethod,
  type PaymentStatus,
  type PurchaseDetails,
  type PurchaseDocument,
  type PurchaseKind,
} from "@/purchases/api";
import { useExchangeRate, useRegisterPurchaseDocument } from "@/purchases/hooks";

const KIND_OPTIONS: { value: PurchaseKind; label: string }[] = [
  { value: "receipt", label: "Receipt" },
  { value: "invoice", label: "Invoice" },
  { value: "card_invoice", label: "Card invoice" },
  { value: "other", label: "Other" },
];

const METHOD_LABEL: Record<PaymentMethod, string> = {
  card: "Card",
  bank_transfer: "Bank transfer",
  direct_debit: "Direct debit",
  cash: "Cash",
  private: "Paid privately",
};

function methodOptions(kind: PurchaseKind) {
  return (Object.keys(METHOD_LABEL) as PaymentMethod[])
    .filter((method) => !(kind === "card_invoice" && method === "card"))
    .map((value) => ({ value, label: METHOD_LABEL[value] }));
}

const STATUS_OPTIONS: { value: PaymentStatus; label: string }[] = [
  { value: "unpaid", label: "Not paid yet" },
  { value: "paid", label: "Already paid" },
];

type Values = {
  kind: PurchaseKind;
  vendor: string;
  documentNo: string;
  description: string;
  documentDate: string;
  dueDate: string;
  paymentStatus: PaymentStatus;
  paidOn: string;
  paymentMethod: PaymentMethod | "";
  amount: string;
  currency: string;
  vatAmount: string;
  amountBase: string;
};

function initialValues(baseCurrency: string): Values {
  return {
    kind: "receipt",
    vendor: "",
    documentNo: "",
    description: "",
    documentDate: "",
    dueDate: "",
    paymentStatus: "unpaid",
    paidOn: "",
    paymentMethod: "",
    amount: "",
    currency: baseCurrency,
    vatAmount: "",
    amountBase: "",
  };
}

function money(value: number): string {
  return value.toLocaleString("sv-SE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function detailsFrom(values: Values): PurchaseDetails {
  const isOther = values.kind === "other";
  const isInvoice = values.kind === "invoice" || values.kind === "card_invoice";
  const paid = values.kind === "receipt" || values.paymentStatus === "paid";
  return {
    kind: values.kind,
    vendor: values.vendor || null,
    document_no: values.documentNo || null,
    description: values.description || null,
    document_date: values.documentDate || null,
    due_date: isInvoice && !paid ? values.dueDate || null : null,
    payment_status: isInvoice ? values.paymentStatus : null,
    paid_on: isInvoice && paid ? values.paidOn || null : null,
    payment_method: !isOther && paid ? values.paymentMethod || null : null,
    amount: isOther ? null : values.amount || null,
    currency: isOther ? null : values.currency.toUpperCase() || null,
    vat_amount: isOther ? null : values.vatAmount || null,
    amount_base: isOther ? null : values.amountBase || null,
  };
}

/** Classifies one inbox document. The form is keyed by the document's id by its parent, so
 * switching documents starts a fresh one. */
export function PurchaseRegisterForm({
  document,
  baseCurrency,
  onRegistered,
}: {
  document: PurchaseDocument;
  baseCurrency: string;
  onRegistered?: () => void;
}) {
  const register = useRegisterPurchaseDocument();
  const [values, setValues] = useState<Values>(initialValues(baseCurrency));
  const [error, setError] = useState<string | null>(null);

  function patch(change: Partial<Values>) {
    setValues((previous) => ({ ...previous, ...change }));
  }

  const isOther = values.kind === "other";
  const isInvoice = values.kind === "invoice" || values.kind === "card_invoice";
  const paid = values.kind === "receipt" || values.paymentStatus === "paid";
  const cardReceipt = !isInvoice && !isOther && values.paymentMethod === "card";

  // Live base-currency preview: the rate of the payment date for a paid document, else of the
  // document date (provisional until it is paid), exactly what the backend will apply.
  const currency = values.currency.toUpperCase();
  // A receipt is paid on its purchase date; a paid invoice on "Paid on"; an unpaid one has none.
  let rateDate = values.documentDate;
  if (isInvoice && paid) rateDate = values.paidOn;
  const amount = Number(values.amount);
  const needsRate =
    !isOther &&
    !cardReceipt &&
    /^[A-Z]{3}$/.test(currency) &&
    currency !== baseCurrency &&
    amount > 0 &&
    rateDate !== "" &&
    values.amountBase === "";
  const rate = useExchangeRate(currency, rateDate, needsRate);

  let preview: string | null = null;
  if (cardReceipt) {
    preview = `The ${baseCurrency} amount comes from the card invoice this receipt is settled by.`;
  } else if (!isOther && amount > 0 && currency === baseCurrency) {
    preview = `${money(amount)} ${baseCurrency}`;
  } else if (needsRate && rate.data) {
    const converted = amount * Number(rate.data.rate);
    preview =
      `≈ ${money(converted)} ${baseCurrency} at ${rate.data.rate} (rate of ${rate.data.rate_date})` +
      (paid ? "" : " — provisional until paid");
  }
  const rateMissing = needsRate && rate.isError;

  async function handleSubmit() {
    setError(null);
    try {
      await register.mutateAsync({ documentId: document.id, details: detailsFrom(values) });
      notifications.show({ title: "Document registered", message: document.file_name });
      onRegistered?.();
    } catch (registerError) {
      if (registerError instanceof PurchaseRuleError || registerError instanceof PurchaseConflictError) {
        setError(registerError.message);
        return;
      }
      throw registerError;
    }
  }

  const dateLabel = values.kind === "receipt" ? "Purchase date" : "Document date";

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void handleSubmit();
      }}
    >
      <Stack gap="sm">
        <SegmentedControl
          aria-label="Kind"
          fullWidth
          data={KIND_OPTIONS}
          value={values.kind}
          onChange={(value) => {
            const kind = value as PurchaseKind;
            patch({
              kind,
              paymentMethod:
                kind === "card_invoice" && values.paymentMethod === "card" ? "" : values.paymentMethod,
            });
          }}
        />
        {error && <Alert color="red">{error}</Alert>}
        <TextInput label="Vendor" value={values.vendor} onChange={(e) => patch({ vendor: e.currentTarget.value })} />
        <Group grow align="flex-start">
          <TextInput
            label="Document no."
            value={values.documentNo}
            onChange={(e) => patch({ documentNo: e.currentTarget.value })}
          />
          <DateInput
            label={dateLabel}
            required={!isOther}
            value={values.documentDate}
            onChange={(value) => patch({ documentDate: value ?? "" })}
          />
        </Group>
        <TextInput
          label="Description"
          value={values.description}
          onChange={(e) => patch({ description: e.currentTarget.value })}
        />
        {!isOther && (
          <>
            <Group grow align="flex-start">
              <NumberInput
                label="Amount (incl. VAT)"
                required
                decimalScale={2}
                min={0}
                value={values.amount === "" ? "" : Number(values.amount)}
                onChange={(value) => patch({ amount: value === "" ? "" : String(value) })}
              />
              <TextInput
                label="Currency"
                required
                maxLength={3}
                value={values.currency}
                onChange={(e) => patch({ currency: e.currentTarget.value.toUpperCase() })}
              />
              <NumberInput
                label="VAT"
                decimalScale={2}
                min={0}
                value={values.vatAmount === "" ? "" : Number(values.vatAmount)}
                onChange={(value) => patch({ vatAmount: value === "" ? "" : String(value) })}
              />
            </Group>
            {isInvoice && (
              <Select
                label="Payment"
                allowDeselect={false}
                data={STATUS_OPTIONS}
                value={values.paymentStatus}
                onChange={(value) => patch({ paymentStatus: (value ?? "unpaid") as PaymentStatus })}
              />
            )}
            {isInvoice && !paid && (
              <DateInput
                label="Due date"
                required
                value={values.dueDate}
                onChange={(value) => patch({ dueDate: value ?? "" })}
              />
            )}
            {isInvoice && paid && (
              <DateInput
                label="Paid on"
                required
                value={values.paidOn}
                onChange={(value) => patch({ paidOn: value ?? "" })}
              />
            )}
            {paid && (
              <Select
                label="Payment method"
                required
                data={methodOptions(values.kind)}
                value={values.paymentMethod || null}
                onChange={(value) => patch({ paymentMethod: (value ?? "") as PaymentMethod | "" })}
              />
            )}
            {!cardReceipt && currency !== baseCurrency && (
              <NumberInput
                label={`${baseCurrency} amount (optional)`}
                description="Overrides the automatic conversion, e.g. what the bank actually debited."
                decimalScale={2}
                min={0}
                value={values.amountBase === "" ? "" : Number(values.amountBase)}
                onChange={(value) => patch({ amountBase: value === "" ? "" : String(value) })}
              />
            )}
            {preview && (
              <Text size="sm" c="dimmed" aria-label="Base currency preview">
                {preview}
              </Text>
            )}
            {rateMissing && (
              <Text size="sm" c="orange">
                No exchange rate is published for this date — type the {baseCurrency} amount above.
              </Text>
            )}
          </>
        )}
        <Group justify="flex-end">
          <Button type="submit" loading={register.isPending}>
            Register
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
