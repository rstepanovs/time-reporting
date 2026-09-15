import { Button, Modal, NumberInput, Select, Stack, Textarea, TextInput } from "@mantine/core";
import { isNotEmpty, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";

import type { BillingItem, BillingUnit } from "@/projects/api";
import { BillingItemConflictError } from "@/projects/api";
import { useAddProjectBillingItem, useUpdateProjectBillingItem } from "@/projects/hooks";

export const BILLING_UNIT_LABELS: Record<BillingUnit, string> = {
  hour: "Per hour",
  day: "Per day",
  amount: "Expense at cost",
};

const UNIT_OPTIONS = (Object.keys(BILLING_UNIT_LABELS) as BillingUnit[]).map((value) => ({
  value,
  label: BILLING_UNIT_LABELS[value],
}));

/** e.g. "90.00 EUR / hour", "At cost + 10.00%", "At cost", "Not set". */
export function formatBillingItemPrice(item: BillingItem, currency: string): string {
  if (item.unit === "amount") {
    return item.markup_percent !== null ? `At cost + ${item.markup_percent}%` : "At cost";
  }
  return item.unit_rate !== null ? `${item.unit_rate} ${currency} / ${item.unit}` : "Not set";
}

type FormValues = {
  name: string;
  unit: BillingUnit;
  description: string;
  unitRate: number | "";
  markupPercent: number | "";
};

type Props =
  | { mode: "create"; opened: boolean; onClose: () => void; projectId: string; currency: string }
  | {
      mode: "edit";
      opened: boolean;
      onClose: () => void;
      projectId: string;
      currency: string;
      item: BillingItem;
    };

/** Create or edit a project's billing item. The unit can't change once an item exists (it decides
 * whether a rate or a markup applies), so it's locked in edit mode. */
export function BillingItemFormModal(props: Props) {
  const { opened, onClose, projectId, currency } = props;
  const addItem = useAddProjectBillingItem(projectId);
  const updateItem = useUpdateProjectBillingItem(projectId);
  const mutation = props.mode === "create" ? addItem : updateItem;

  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues:
      props.mode === "edit"
        ? {
            name: props.item.name,
            unit: props.item.unit,
            description: props.item.description ?? "",
            unitRate: props.item.unit_rate !== null ? Number(props.item.unit_rate) : "",
            markupPercent:
              props.item.markup_percent !== null ? Number(props.item.markup_percent) : "",
          }
        : { name: "", unit: "hour", description: "", unitRate: "", markupPercent: "" },
    validate: {
      name: isNotEmpty("Enter a name"),
    },
  });

  const unit = form.getValues().unit;

  const handleSubmit = form.onSubmit(async (values) => {
    try {
      if (props.mode === "create") {
        const created = await addItem.mutateAsync({
          name: values.name,
          unit: values.unit,
          description: values.description || null,
          unit_rate: values.unit === "amount" || values.unitRate === "" ? null : values.unitRate,
          markup_percent:
            values.unit === "amount" && values.markupPercent !== "" ? values.markupPercent : null,
        });
        onClose();
        notifications.show({ title: "Billing item added", message: created.name });
      } else {
        const original = props.item;
        const body: {
          name?: string;
          description?: string | null;
          unit_rate?: number | string | null;
          markup_percent?: number | string | null;
        } = {};
        if (values.name !== original.name) body.name = values.name;
        const newDescription = values.description || null;
        if (newDescription !== original.description) body.description = newDescription;
        if (original.unit === "amount") {
          const newMarkup = values.markupPercent === "" ? null : values.markupPercent;
          const originalMarkup =
            original.markup_percent === null ? null : Number(original.markup_percent);
          if (newMarkup !== originalMarkup) body.markup_percent = newMarkup;
        } else {
          const newRate = values.unitRate === "" ? null : values.unitRate;
          const originalRate = original.unit_rate === null ? null : Number(original.unit_rate);
          if (newRate !== originalRate) body.unit_rate = newRate;
        }
        await updateItem.mutateAsync({ itemId: original.id, body });
        onClose();
        notifications.show({ title: "Billing item updated", message: values.name });
      }
    } catch (error) {
      if (error instanceof BillingItemConflictError) {
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
      title={props.mode === "create" ? "Add billing item" : "Edit billing item"}
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
          <Select
            label="Unit"
            required
            allowDeselect={false}
            disabled={props.mode === "edit"}
            description={props.mode === "edit" ? "Can't be changed after creation" : undefined}
            data={UNIT_OPTIONS}
            key={form.key("unit")}
            {...form.getInputProps("unit")}
          />
          {unit === "amount" ? (
            <NumberInput
              label="Markup"
              description="Added on top of the entered expense amount"
              min={0}
              max={1000}
              decimalScale={2}
              suffix="%"
              key={form.key("markupPercent")}
              {...form.getInputProps("markupPercent")}
            />
          ) : (
            <NumberInput
              label="Rate"
              min={0}
              decimalScale={2}
              suffix={` ${currency} / ${unit}`}
              key={form.key("unitRate")}
              {...form.getInputProps("unitRate")}
            />
          )}
          <Textarea
            label="Description"
            autosize
            minRows={2}
            key={form.key("description")}
            {...form.getInputProps("description")}
          />
          <Button type="submit" loading={mutation.isPending} style={{ alignSelf: "flex-start" }}>
            {props.mode === "create" ? "Add billing item" : "Save changes"}
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
