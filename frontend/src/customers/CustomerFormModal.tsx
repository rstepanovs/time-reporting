import {
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Textarea,
  TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { isNotEmpty, matches, useForm } from "@mantine/form";

import { INVOICE_LOCALE_OPTIONS } from "@/company/api";
import type { Customer, CustomerCreateBody, CustomerUpdateBody, InvoiceLocale } from "@/customers/api";
import { CustomerConflictError } from "@/customers/api";
import { useCreateCustomer, useUpdateCustomer } from "@/customers/hooks";

const INTERVAL_UNIT_OPTIONS = [
  { value: "day", label: "day(s)" },
  { value: "week", label: "week(s)" },
  { value: "month", label: "month(s)" },
  { value: "year", label: "year(s)" },
];

// "" means "use the company's default", stored as `invoice_locale: null`.
const INVOICE_LOCALE_SELECT_OPTIONS = [
  { value: "", label: "Company default" },
  ...INVOICE_LOCALE_OPTIONS,
];

type FormValues = {
  name: string;
  legalName: string;
  taxId: string;
  billingEmail: string;
  notes: string;
  line1: string;
  line2: string;
  city: string;
  region: string;
  postalCode: string;
  country: string;
  intervalCount: number;
  intervalUnit: string;
  anchorDate: string;
  currency: string;
  paymentTermsDays: number;
  vatRate: number | "";
  vatNote: string;
  invoiceLocale: InvoiceLocale | "";
  customerNumber: string;
  yourReference: string;
};

type Props =
  | { mode: "create"; opened: boolean; onClose: () => void }
  | { mode: "edit"; opened: boolean; onClose: () => void; customer: Customer };

function valuesFromCustomer(customer: Customer): FormValues {
  return {
    name: customer.name,
    legalName: customer.legal_name ?? "",
    taxId: customer.tax_id ?? "",
    billingEmail: customer.billing_email ?? "",
    notes: customer.notes ?? "",
    line1: customer.billing_address.line1,
    line2: customer.billing_address.line2 ?? "",
    city: customer.billing_address.city,
    region: customer.billing_address.region ?? "",
    postalCode: customer.billing_address.postal_code ?? "",
    country: customer.billing_address.country,
    intervalCount: customer.billing_period.interval_count,
    intervalUnit: customer.billing_period.interval_unit,
    anchorDate: customer.billing_period.anchor_date,
    currency: customer.currency,
    paymentTermsDays: customer.payment_terms_days,
    vatRate: customer.vat_rate !== null ? Number(customer.vat_rate) : "",
    vatNote: customer.vat_note ?? "",
    invoiceLocale: (customer.invoice_locale as InvoiceLocale | null) ?? "",
    customerNumber: customer.customer_number ?? "",
    yourReference: customer.your_reference ?? "",
  };
}

const EMPTY_VALUES: FormValues = {
  name: "",
  legalName: "",
  taxId: "",
  billingEmail: "",
  notes: "",
  line1: "",
  line2: "",
  city: "",
  region: "",
  postalCode: "",
  country: "",
  intervalCount: 1,
  intervalUnit: "month",
  anchorDate: "",
  currency: "",
  paymentTermsDays: 30,
  vatRate: "",
  vatNote: "",
  invoiceLocale: "",
  customerNumber: "",
  yourReference: "",
};

/** `null` if cleared (was non-empty, now empty), the new value if changed, `undefined` if unchanged. */
function clearableDiff(original: string, next: string): string | null | undefined {
  const trimmed = next.trim();
  if (trimmed === original) return undefined;
  return trimmed === "" ? null : trimmed;
}

export function CustomerFormModal(props: Props) {
  const { opened, onClose } = props;
  const createCustomer = useCreateCustomer();
  const updateCustomer = useUpdateCustomer(props.mode === "edit" ? props.customer.id : "");

  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues: props.mode === "edit" ? valuesFromCustomer(props.customer) : EMPTY_VALUES,
    validate: {
      name: isNotEmpty("Enter a name"),
      line1: isNotEmpty("Enter an address"),
      city: isNotEmpty("Enter a city"),
      country: matches(/^[A-Za-z]{2}$/, "Use a 2-letter country code, e.g. DE"),
      currency: matches(/^[A-Za-z]{3}$/, "Use a 3-letter currency code, e.g. EUR"),
      anchorDate: isNotEmpty("Choose an anchor date"),
      intervalCount: (value) => (value >= 1 && value <= 366 ? null : "Use 1 to 366"),
      paymentTermsDays: (value) => (value >= 0 && value <= 365 ? null : "Use 0 to 365"),
      vatRate: (value) => (value === "" || (value >= 0 && value <= 100) ? null : "Use 0 to 100"),
    },
  });

  const mutation = props.mode === "create" ? createCustomer : updateCustomer;

  const handleSubmit = form.onSubmit(async (values) => {
    const billingAddress = {
      line1: values.line1,
      line2: values.line2 || null,
      city: values.city,
      region: values.region || null,
      postal_code: values.postalCode || null,
      country: values.country.toUpperCase(),
    };
    const billingPeriod = {
      interval_count: values.intervalCount,
      interval_unit: values.intervalUnit as CustomerCreateBody["billing_period"]["interval_unit"],
      anchor_date: values.anchorDate,
    };

    try {
      if (props.mode === "create") {
        await createCustomer.mutateAsync({
          name: values.name,
          legal_name: values.legalName || null,
          tax_id: values.taxId || null,
          billing_email: values.billingEmail || null,
          notes: values.notes || null,
          billing_address: billingAddress,
          billing_period: billingPeriod,
          currency: values.currency.toUpperCase(),
          payment_terms_days: values.paymentTermsDays,
          vat_rate: values.vatRate === "" ? null : values.vatRate,
          vat_note: values.vatNote || null,
          invoice_locale: values.invoiceLocale || null,
          customer_number: values.customerNumber || null,
          your_reference: values.yourReference || null,
        });
      } else {
        const original = props.customer;
        const body: CustomerUpdateBody = {};
        if (values.name !== original.name) body.name = values.name;
        const legalName = clearableDiff(original.legal_name ?? "", values.legalName);
        if (legalName !== undefined) body.legal_name = legalName;
        const taxId = clearableDiff(original.tax_id ?? "", values.taxId);
        if (taxId !== undefined) body.tax_id = taxId;
        const billingEmail = clearableDiff(original.billing_email ?? "", values.billingEmail);
        if (billingEmail !== undefined) body.billing_email = billingEmail;
        const notes = clearableDiff(original.notes ?? "", values.notes);
        if (notes !== undefined) body.notes = notes;

        const addressChanged =
          billingAddress.line1 !== original.billing_address.line1 ||
          billingAddress.line2 !== original.billing_address.line2 ||
          billingAddress.city !== original.billing_address.city ||
          billingAddress.region !== original.billing_address.region ||
          billingAddress.postal_code !== original.billing_address.postal_code ||
          billingAddress.country !== original.billing_address.country;
        if (addressChanged) body.billing_address = billingAddress;

        const periodChanged =
          billingPeriod.interval_count !== original.billing_period.interval_count ||
          billingPeriod.interval_unit !== original.billing_period.interval_unit ||
          billingPeriod.anchor_date !== original.billing_period.anchor_date;
        if (periodChanged) body.billing_period = billingPeriod;

        const currency = values.currency.toUpperCase();
        if (currency !== original.currency) body.currency = currency;
        if (values.paymentTermsDays !== original.payment_terms_days) {
          body.payment_terms_days = values.paymentTermsDays;
        }

        const newVatRate = values.vatRate === "" ? null : values.vatRate;
        const originalVatRate = original.vat_rate === null ? null : Number(original.vat_rate);
        if (newVatRate !== originalVatRate) body.vat_rate = newVatRate;
        const vatNote = clearableDiff(original.vat_note ?? "", values.vatNote);
        if (vatNote !== undefined) body.vat_note = vatNote;
        const newInvoiceLocale = values.invoiceLocale || null;
        if (newInvoiceLocale !== (original.invoice_locale ?? null)) {
          body.invoice_locale = newInvoiceLocale;
        }
        const customerNumber = clearableDiff(original.customer_number ?? "", values.customerNumber);
        if (customerNumber !== undefined) body.customer_number = customerNumber;
        const yourReference = clearableDiff(original.your_reference ?? "", values.yourReference);
        if (yourReference !== undefined) body.your_reference = yourReference;

        await updateCustomer.mutateAsync(body);
      }
      onClose();
    } catch (error) {
      if (error instanceof CustomerConflictError) {
        form.setFieldError("name", error.message);
      } else {
        throw error;
      }
    }
  });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={props.mode === "create" ? "New customer" : "Edit customer"}
      size="lg"
    >
      <form noValidate onSubmit={handleSubmit}>
        <Stack>
          <TextInput
            label="Name"
            required
            maxLength={255}
            key={form.key("name")}
            {...form.getInputProps("name")}
          />
          <Group grow>
            <TextInput
              label="Legal name"
              maxLength={255}
              key={form.key("legalName")}
              {...form.getInputProps("legalName")}
            />
            <TextInput
              label="Tax ID"
              maxLength={64}
              key={form.key("taxId")}
              {...form.getInputProps("taxId")}
            />
          </Group>
          <TextInput
            label="Billing email"
            type="email"
            key={form.key("billingEmail")}
            {...form.getInputProps("billingEmail")}
          />

          <Group grow>
            <TextInput
              label="Address line 1"
              required
              key={form.key("line1")}
              {...form.getInputProps("line1")}
            />
            <TextInput label="Address line 2" key={form.key("line2")} {...form.getInputProps("line2")} />
          </Group>
          <Group grow>
            <TextInput
              label="City"
              required
              key={form.key("city")}
              {...form.getInputProps("city")}
            />
            <TextInput label="Region" key={form.key("region")} {...form.getInputProps("region")} />
            <TextInput
              label="Postal code"
              key={form.key("postalCode")}
              {...form.getInputProps("postalCode")}
            />
            <TextInput
              label="Country"
              description="2-letter code"
              required
              maxLength={2}
              key={form.key("country")}
              {...form.getInputProps("country")}
            />
          </Group>

          <Group grow align="flex-end">
            <NumberInput
              label="Billing period"
              description="Repeats every"
              required
              min={1}
              max={366}
              key={form.key("intervalCount")}
              {...form.getInputProps("intervalCount")}
            />
            <Select
              label=" "
              data={INTERVAL_UNIT_OPTIONS}
              allowDeselect={false}
              key={form.key("intervalUnit")}
              {...form.getInputProps("intervalUnit")}
            />
            <DateInput
              label="Anchor date"
              required
              key={form.key("anchorDate")}
              {...form.getInputProps("anchorDate")}
            />
          </Group>

          <Group grow>
            <TextInput
              label="Currency"
              description="3-letter code"
              required
              maxLength={3}
              key={form.key("currency")}
              {...form.getInputProps("currency")}
            />
            <NumberInput
              label="Payment terms (days)"
              required
              min={0}
              max={365}
              key={form.key("paymentTermsDays")}
              {...form.getInputProps("paymentTermsDays")}
            />
          </Group>

          <Textarea
            label="Notes"
            autosize
            minRows={2}
            key={form.key("notes")}
            {...form.getInputProps("notes")}
          />

          <Group grow align="flex-end">
            <NumberInput
              label="VAT rate"
              description="Blank prints no VAT line, e.g. for reverse charge"
              min={0}
              max={100}
              decimalScale={2}
              suffix="%"
              key={form.key("vatRate")}
              {...form.getInputProps("vatRate")}
            />
            <Select
              label="Invoice language"
              data={INVOICE_LOCALE_SELECT_OPTIONS}
              allowDeselect={false}
              key={form.key("invoiceLocale")}
              {...form.getInputProps("invoiceLocale")}
            />
          </Group>
          <Textarea
            label="VAT note"
            description={'Printed on the invoice, e.g. "Omvänd betalningsskyldighet / Reverse charge"'}
            autosize
            minRows={2}
            key={form.key("vatNote")}
            {...form.getInputProps("vatNote")}
          />
          <Group grow>
            <TextInput
              label="Customer number"
              description={
                props.mode === "create" ? "Left blank, one is assigned automatically" : undefined
              }
              maxLength={50}
              key={form.key("customerNumber")}
              {...form.getInputProps("customerNumber")}
            />
            <TextInput
              label="Your reference"
              maxLength={255}
              key={form.key("yourReference")}
              {...form.getInputProps("yourReference")}
            />
          </Group>

          <Button type="submit" loading={mutation.isPending} style={{ alignSelf: "flex-start" }}>
            {props.mode === "create" ? "Create customer" : "Save changes"}
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
