import { Alert, Button, Modal, NumberInput, Select, Stack, Textarea, TextInput } from "@mantine/core";
import { isNotEmpty, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useNavigate } from "react-router";

import { useCustomers } from "@/customers/hooks";
import type { Project } from "@/projects/api";
import { ProjectConflictError, ProjectRuleError } from "@/projects/api";
import { useCreateProject, useUpdateProject } from "@/projects/hooks";

const DEFAULT_NORMAL_WORKING_HOURS = 8;

type FormValues = {
  customerId: string;
  name: string;
  description: string;
  normalWorkingHours: number | string;
};

type Props =
  | {
      mode: "create";
      opened: boolean;
      onClose: () => void;
      defaultCustomerId?: string;
      /** Called instead of navigating to the new project's page, e.g. from the admin list. */
      onCreated?: (project: Project) => void;
    }
  | { mode: "edit"; opened: boolean; onClose: () => void; project: Project };

export function ProjectFormModal(props: Props) {
  const { opened, onClose } = props;
  const navigate = useNavigate();
  const customers = useCustomers({ includeInactive: false, limit: 100 });
  const createProject = useCreateProject();
  const updateProject = useUpdateProject(props.mode === "edit" ? props.project.id : "");

  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues:
      props.mode === "edit"
        ? {
            customerId: props.project.customer.id,
            name: props.project.name,
            description: props.project.description ?? "",
            normalWorkingHours: props.project.normal_working_hours,
          }
        : {
            customerId: props.defaultCustomerId ?? "",
            name: "",
            description: "",
            normalWorkingHours: DEFAULT_NORMAL_WORKING_HOURS,
          },
    validate: {
      customerId: isNotEmpty("Choose a customer"),
      name: isNotEmpty("Enter a project name"),
      normalWorkingHours: (value) =>
        value === "" || Number(value) <= 0 || Number(value) > 24
          ? "Enter a value between 0 and 24"
          : null,
    },
  });

  const mutation = props.mode === "create" ? createProject : updateProject;

  const handleSubmit = form.onSubmit(async (values) => {
    try {
      if (props.mode === "create") {
        const created = await createProject.mutateAsync({
          customerId: values.customerId,
          name: values.name,
          description: values.description || null,
          normalWorkingHours: values.normalWorkingHours,
        });
        onClose();
        notifications.show({ title: "Project created", message: created.name });
        if (props.onCreated) {
          props.onCreated(created);
        } else {
          await navigate(`/projects/${created.id}`);
        }
      } else {
        const original = props.project;
        const body: {
          name?: string;
          description?: string | null;
          normal_working_hours?: number | string;
        } = {};
        if (values.name !== original.name) body.name = values.name;
        const newDescription = values.description || null;
        if (newDescription !== original.description) body.description = newDescription;
        if (String(values.normalWorkingHours) !== original.normal_working_hours) {
          body.normal_working_hours = values.normalWorkingHours;
        }
        await updateProject.mutateAsync(body);
        onClose();
        notifications.show({ title: "Project updated", message: values.name });
      }
    } catch (error) {
      if (error instanceof ProjectConflictError) {
        form.setFieldError("name", error.message);
      } else if (!(error instanceof ProjectRuleError)) {
        throw error;
      }
    }
  });

  const ruleError = mutation.error instanceof ProjectRuleError ? mutation.error : null;

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={props.mode === "create" ? "New project" : "Edit project"}
    >
      <form noValidate onSubmit={handleSubmit}>
        <Stack>
          {ruleError && (
            <Alert color="red" variant="light">
              {ruleError.message}
            </Alert>
          )}
          <Select
            label="Customer"
            placeholder="Choose a customer"
            required
            disabled={props.mode === "edit"}
            data={(customers.data?.items ?? []).map((customer) => ({
              value: customer.id,
              label: customer.name,
            }))}
            searchable
            key={form.key("customerId")}
            {...form.getInputProps("customerId")}
          />
          <TextInput
            label="Name"
            required
            maxLength={255}
            key={form.key("name")}
            {...form.getInputProps("name")}
          />
          <Textarea
            label="Description"
            autosize
            minRows={2}
            key={form.key("description")}
            {...form.getInputProps("description")}
          />
          <NumberInput
            label="Normal working hours per day"
            description="Used to prefill a new timesheet week when the worker has just this one project"
            required
            min={0.25}
            max={24}
            step={0.25}
            decimalScale={2}
            key={form.key("normalWorkingHours")}
            {...form.getInputProps("normalWorkingHours")}
          />
          <Button type="submit" loading={mutation.isPending} style={{ alignSelf: "flex-start" }}>
            {props.mode === "create" ? "Create project" : "Save changes"}
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
