import { Alert, Button, Group, Loader, Modal, NumberInput, Select, Stack, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useProjectBillingItems, useProjects } from "@/projects/hooks";
import {
  PurchaseConflictError,
  PurchaseRuleError,
  type PurchaseDocument,
} from "@/purchases/api";
import { useRebillPurchase, useRebillSuggestion } from "@/purchases/hooks";

/** "Rebill to project…": files the document to a project's expense report (the accountant's own,
 * for the month of the expense date). The amount is prefilled in the customer's currency — from
 * the printed amount or converted through the base currency — and stays editable. */
export function RebillModal({
  document,
  opened,
  onClose,
}: {
  document: PurchaseDocument;
  opened: boolean;
  onClose: () => void;
}) {
  const projects = useProjects({ limit: 200 });
  const [projectId, setProjectId] = useState("");
  const [billingItemId, setBillingItemId] = useState("");
  const [expenseDate, setExpenseDate] = useState(document.document_date ?? "");
  // `null` = untouched, so the server's suggestion shows; a string is what the user typed.
  const [amount, setAmount] = useState<string | null>(null);
  const [description, setDescription] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const billingItems = useProjectBillingItems(projectId);
  const suggestion = useRebillSuggestion(document.id, projectId);
  const rebill = useRebillPurchase();

  const items = (billingItems.data ?? []).filter((item) => item.unit === "amount" && item.is_active);
  const shownAmount = amount ?? suggestion.data?.amount ?? "";
  const shownDescription = description ?? suggestion.data?.description ?? "";
  const currency = suggestion.data?.currency ?? "";
  const [year, month] = expenseDate.split("-").map(Number);
  const ready =
    projectId !== "" &&
    billingItemId !== "" &&
    expenseDate !== "" &&
    Number(shownAmount) > 0 &&
    shownDescription.trim() !== "";

  async function handleSubmit() {
    setError(null);
    try {
      await rebill.mutateAsync({
        documentId: document.id,
        projectId,
        year,
        month,
        billingItemId,
        description: shownDescription.trim(),
        amount: String(shownAmount),
        expenseDate,
      });
      notifications.show({
        title: "Rebilled",
        message: "Added to your expense report for the project. Submit it for approval there.",
      });
      onClose();
    } catch (rebillError) {
      if (rebillError instanceof PurchaseConflictError || rebillError instanceof PurchaseRuleError) {
        setError(rebillError.message);
        return;
      }
      throw rebillError;
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Rebill to a project">
      <Stack>
        <Text size="sm" c="dimmed">
          A copy of the file is added to your own expense report for the project and month; submit
          and approve that report as usual.
        </Text>
        {error && <Alert color="red">{error}</Alert>}
        <Select
          label="Project"
          required
          searchable
          data={(projects.data?.items ?? [])
            .filter((project) => project.is_active)
            .map((project) => ({
              value: project.id,
              label: `${project.name} (${project.customer.name})`,
            }))}
          value={projectId || null}
          onChange={(value) => {
            setProjectId(value ?? "");
            setBillingItemId("");
            setAmount(null);
            setDescription(null);
          }}
        />
        {projectId !== "" && billingItems.isLoading && <Loader size="sm" />}
        {projectId !== "" && billingItems.isSuccess && items.length === 0 && (
          <Alert color="yellow">
            This project has no active expense (amount) billing item to rebill against.
          </Alert>
        )}
        {items.length > 0 && (
          <Select
            label="Billing item"
            required
            data={items.map((item) => ({ value: item.id, label: item.name }))}
            value={billingItemId || null}
            onChange={(value) => setBillingItemId(value ?? "")}
          />
        )}
        <DateInput
          label="Expense date"
          required
          value={expenseDate}
          onChange={(value) => setExpenseDate(value ?? "")}
          description="Its month decides which expense report the line goes on."
        />
        <NumberInput
          label={currency ? `Amount (${currency})` : "Amount"}
          required
          decimalScale={2}
          min={0}
          value={shownAmount === "" ? "" : Number(shownAmount)}
          onChange={(value) => setAmount(value === "" ? "" : String(value))}
        />
        {projectId !== "" && suggestion.isSuccess && suggestion.data.amount === null && (
          <Text size="xs" c="orange">
            The amount can't be derived automatically (no amount in {currency} or no rate) — type it
            in.
          </Text>
        )}
        <TextInput
          label="Description"
          required
          value={shownDescription}
          onChange={(event) => setDescription(event.currentTarget.value)}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={rebill.isPending} disabled={!ready} onClick={() => void handleSubmit()}>
            Rebill
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
