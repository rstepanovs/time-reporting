import { Button, Modal, Select, Stack, TextInput } from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { isNotEmpty, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";

import { NonWorkingDayConflictError, type NonWorkingDay, type NonWorkingDayKind } from "@/calendar/api";
import { useAddNonWorkingDay, useUpdateNonWorkingDay } from "@/calendar/hooks";

export const NON_WORKING_DAY_KIND_LABELS: Record<NonWorkingDayKind, string> = {
  public_holiday: "Public holiday",
  bridge_day: "Bridge day",
  company_day_off: "Company day off",
};

const KIND_OPTIONS = (Object.keys(NON_WORKING_DAY_KIND_LABELS) as NonWorkingDayKind[]).map((value) => ({
  value,
  label: NON_WORKING_DAY_KIND_LABELS[value],
}));

type FormValues = { day: string | null; name: string; kind: NonWorkingDayKind };

type Props =
  | { mode: "create"; opened: boolean; onClose: () => void }
  | { mode: "edit"; opened: boolean; onClose: () => void; day: NonWorkingDay };

/** Create or edit a non-working day. `kind` can't change once it exists, so it's locked in edit
 * mode, matching how a billing item's unit is locked. */
export function NonWorkingDayFormModal(props: Props) {
  const { opened, onClose } = props;
  const addDay = useAddNonWorkingDay();
  const updateDay = useUpdateNonWorkingDay(props.mode === "edit" ? props.day.id : "");
  const mutation = props.mode === "create" ? addDay : updateDay;

  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues:
      props.mode === "edit"
        ? { day: props.day.day, name: props.day.name, kind: props.day.kind }
        : { day: null, name: "", kind: "company_day_off" },
    validate: {
      day: (value) => (value ? null : "Choose a date"),
      name: isNotEmpty("Enter a name"),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    if (!values.day) return;
    try {
      if (props.mode === "create") {
        const created = await addDay.mutateAsync({
          day: values.day,
          name: values.name,
          kind: values.kind,
        });
        onClose();
        notifications.show({ title: "Non-working day added", message: created.name });
      } else {
        await updateDay.mutateAsync({ day: values.day, name: values.name });
        onClose();
        notifications.show({ title: "Non-working day updated", message: values.name });
      }
    } catch (error) {
      if (error instanceof NonWorkingDayConflictError) {
        form.setFieldError("day", error.message);
      } else {
        throw error;
      }
    }
  });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={props.mode === "create" ? "Add a non-working day" : "Edit non-working day"}
    >
      <form noValidate onSubmit={handleSubmit}>
        <Stack>
          <DatePickerInput
            label="Date"
            required
            key={form.key("day")}
            {...form.getInputProps("day")}
          />
          <TextInput
            label="Name"
            required
            maxLength={255}
            key={form.key("name")}
            {...form.getInputProps("name")}
          />
          <Select
            label="Kind"
            required
            allowDeselect={false}
            disabled={props.mode === "edit"}
            description={props.mode === "edit" ? "Can't be changed after creation" : undefined}
            data={KIND_OPTIONS}
            key={form.key("kind")}
            {...form.getInputProps("kind")}
          />
          <Button type="submit" loading={mutation.isPending} style={{ alignSelf: "flex-start" }}>
            {props.mode === "create" ? "Add day" : "Save changes"}
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
