import {
  Alert,
  Avatar,
  Button,
  Checkbox,
  FileInput,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { isEmail, matches, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  companyLogoUrl,
  CompanyLogoTooLargeError,
  CompanyLogoTypeError,
  INVOICE_LOCALE_OPTIONS,
  type CompanySettings,
  type CompanySettingsUpdateBody,
  type InvoiceLocale,
} from "@/company/api";
import {
  useClearCompanyLogo,
  useCompanySettings,
  useSetCompanyLogo,
  useUpdateCompanySettings,
} from "@/company/hooks";

type FormValues = {
  legalName: string;
  orgNumber: string;
  vatNumber: string;
  street: string;
  street2: string;
  postalCode: string;
  city: string;
  country: string;
  email: string;
  phone: string;
  registeredOffice: string;
  fTaxApproved: boolean;
  bankgiro: string;
  iban: string;
  bic: string;
  defaultInvoiceLocale: InvoiceLocale;
  lateInterest: string;
  invoiceNumberPrefix: string;
  nextInvoiceNumber: number;
  customerNumberPrefix: string;
  nextCustomerNumber: number;
  allowSelfReview: boolean;
};

function valuesFromSettings(settings: CompanySettings): FormValues {
  return {
    legalName: settings.legal_name,
    orgNumber: settings.org_number,
    vatNumber: settings.vat_number,
    street: settings.address.street,
    street2: settings.address.street2 ?? "",
    postalCode: settings.address.postal_code,
    city: settings.address.city,
    country: settings.address.country,
    email: settings.email,
    phone: settings.phone,
    registeredOffice: settings.registered_office,
    fTaxApproved: settings.f_tax_approved,
    bankgiro: settings.bankgiro,
    iban: settings.iban,
    bic: settings.bic,
    defaultInvoiceLocale: settings.default_invoice_locale as InvoiceLocale,
    lateInterest: settings.late_interest,
    invoiceNumberPrefix: settings.invoice_number_prefix,
    nextInvoiceNumber: settings.next_invoice_number,
    customerNumberPrefix: settings.customer_number_prefix,
    nextCustomerNumber: settings.next_customer_number,
    allowSelfReview: settings.allow_self_review,
  };
}

function LogoCard({ settings }: { settings: CompanySettings }) {
  const setLogo = useSetCompanyLogo();
  const clearLogo = useClearCompanyLogo();
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function handleUpload(file: File | null) {
    if (!file) return;
    setUploadError(null);
    try {
      await setLogo.mutateAsync(file);
      notifications.show({ title: "Logo updated", message: "" });
    } catch (error) {
      if (error instanceof CompanyLogoTooLargeError || error instanceof CompanyLogoTypeError) {
        setUploadError(error.message);
        return;
      }
      throw error;
    }
  }

  async function handleRemove() {
    await clearLogo.mutateAsync();
    notifications.show({ title: "Logo removed", message: "" });
  }

  return (
    <Stack gap="xs">
      <Title order={4}>Logo</Title>
      {uploadError && (
        <Alert color="red" onClose={() => setUploadError(null)} withCloseButton>
          {uploadError}
        </Alert>
      )}
      <Group>
        <Avatar
          src={settings.has_logo ? `${companyLogoUrl()}?t=${encodeURIComponent(settings.updated_at)}` : null}
          alt="Company logo"
          size={64}
          radius="sm"
        />
        <FileInput
          aria-label="Upload logo"
          placeholder="Choose a file…"
          accept="image/svg+xml,image/png,image/jpeg"
          value={null}
          onChange={(file) => void handleUpload(file)}
          disabled={setLogo.isPending}
          w={280}
        />
        {settings.has_logo && (
          <Button variant="default" loading={clearLogo.isPending} onClick={() => void handleRemove()}>
            Remove logo
          </Button>
        )}
      </Group>
      <Text size="xs" c="dimmed">
        SVG, PNG or JPEG, up to 512 KB. Printed on issued invoices.
      </Text>
    </Stack>
  );
}

function CompanyForm({ settings }: { settings: CompanySettings }) {
  const updateSettings = useUpdateCompanySettings();

  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues: valuesFromSettings(settings),
    validate: {
      email: (value) => (value === "" || isEmail(value) ? null : "Enter a valid email"),
      country: matches(/^([A-Za-z]{2})?$/, "Use a 2-letter country code, e.g. SE"),
      nextInvoiceNumber: (value) => (value >= 1 ? null : "Use 1 or higher"),
      nextCustomerNumber: (value) => (value >= 1 ? null : "Use 1 or higher"),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    const body: CompanySettingsUpdateBody = {
      legal_name: values.legalName,
      org_number: values.orgNumber,
      vat_number: values.vatNumber,
      address: {
        street: values.street,
        street2: values.street2 || null,
        postal_code: values.postalCode,
        city: values.city,
        country: values.country.toUpperCase(),
      },
      email: values.email,
      phone: values.phone,
      registered_office: values.registeredOffice,
      f_tax_approved: values.fTaxApproved,
      bankgiro: values.bankgiro,
      iban: values.iban,
      bic: values.bic,
      default_invoice_locale: values.defaultInvoiceLocale,
      late_interest: values.lateInterest,
      invoice_number_prefix: values.invoiceNumberPrefix,
      next_invoice_number: values.nextInvoiceNumber,
      customer_number_prefix: values.customerNumberPrefix,
      next_customer_number: values.nextCustomerNumber,
      allow_self_review: values.allowSelfReview,
    };
    await updateSettings.mutateAsync(body);
    notifications.show({ title: "Company settings saved", message: "" });
  });

  return (
    <form noValidate onSubmit={handleSubmit}>
      <Stack>
        <Title order={4}>Company</Title>
        <Group grow>
          <TextInput
            label="Legal name"
            key={form.key("legalName")}
            {...form.getInputProps("legalName")}
          />
          <TextInput
            label="Org number"
            key={form.key("orgNumber")}
            {...form.getInputProps("orgNumber")}
          />
          <TextInput
            label="VAT number"
            key={form.key("vatNumber")}
            {...form.getInputProps("vatNumber")}
          />
        </Group>
        <Group grow>
          <TextInput label="Email" type="email" key={form.key("email")} {...form.getInputProps("email")} />
          <TextInput label="Phone" key={form.key("phone")} {...form.getInputProps("phone")} />
          <TextInput
            label="Registered office"
            description="City of registration"
            key={form.key("registeredOffice")}
            {...form.getInputProps("registeredOffice")}
          />
        </Group>
        <Checkbox
          label="F-tax approved"
          key={form.key("fTaxApproved")}
          {...form.getInputProps("fTaxApproved", { type: "checkbox" })}
        />

        <Title order={4} mt="md">
          Address
        </Title>
        <Group grow>
          <TextInput label="Street" key={form.key("street")} {...form.getInputProps("street")} />
          <TextInput label="Street 2" key={form.key("street2")} {...form.getInputProps("street2")} />
        </Group>
        <Group grow>
          <TextInput
            label="Postal code"
            key={form.key("postalCode")}
            {...form.getInputProps("postalCode")}
          />
          <TextInput label="City" key={form.key("city")} {...form.getInputProps("city")} />
          <TextInput
            label="Country"
            description="2-letter code"
            maxLength={2}
            key={form.key("country")}
            {...form.getInputProps("country")}
          />
        </Group>

        <Title order={4} mt="md">
          Bank
        </Title>
        <Group grow>
          <TextInput label="Bankgiro" key={form.key("bankgiro")} {...form.getInputProps("bankgiro")} />
          <TextInput label="IBAN" key={form.key("iban")} {...form.getInputProps("iban")} />
          <TextInput label="BIC" key={form.key("bic")} {...form.getInputProps("bic")} />
        </Group>

        <Title order={4} mt="md">
          Invoicing
        </Title>
        <Group grow align="flex-end">
          <TextInput
            label="Invoice number prefix"
            key={form.key("invoiceNumberPrefix")}
            {...form.getInputProps("invoiceNumberPrefix")}
          />
          <NumberInput
            label="Next invoice number"
            min={1}
            key={form.key("nextInvoiceNumber")}
            {...form.getInputProps("nextInvoiceNumber")}
          />
          <Select
            label="Default locale"
            data={INVOICE_LOCALE_OPTIONS}
            allowDeselect={false}
            key={form.key("defaultInvoiceLocale")}
            {...form.getInputProps("defaultInvoiceLocale")}
          />
        </Group>
        <TextInput
          label="Late interest"
          description='Printed on invoices, e.g. "Reference rate + 8 %"'
          key={form.key("lateInterest")}
          {...form.getInputProps("lateInterest")}
        />

        <Title order={4} mt="md">
          Customer numbering
        </Title>
        <Text size="xs" c="dimmed">
          A new customer with no number of its own gets the next one from here automatically.
        </Text>
        <Group grow align="flex-end">
          <TextInput
            label="Customer number prefix"
            key={form.key("customerNumberPrefix")}
            {...form.getInputProps("customerNumberPrefix")}
          />
          <NumberInput
            label="Next customer number"
            min={1}
            key={form.key("nextCustomerNumber")}
            {...form.getInputProps("nextCustomerNumber")}
          />
        </Group>

        <Title order={4} mt="md">
          Workflow
        </Title>
        <Switch
          label="Allow self-review"
          description="Lets an admin who is also a manager approve their own timesheet weeks and expense reports — needed for a one-person company, where nobody else can."
          key={form.key("allowSelfReview")}
          {...form.getInputProps("allowSelfReview", { type: "checkbox" })}
        />

        <Button type="submit" loading={updateSettings.isPending} style={{ alignSelf: "flex-start" }}>
          Save changes
        </Button>
      </Stack>
    </form>
  );
}

export function AdminCompanyPage() {
  const settings = useCompanySettings();

  return (
    <Stack>
      <Title order={2}>Company</Title>

      {settings.isPending && <Loader />}
      {settings.isError && <Alert color="red">Could not load company settings.</Alert>}

      {settings.data && (
        <>
          <LogoCard settings={settings.data} />
          <CompanyForm settings={settings.data} />
        </>
      )}
    </Stack>
  );
}
