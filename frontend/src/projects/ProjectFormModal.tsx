import { Alert, Button, Modal, Select, Stack, Textarea, TextInput } from "@mantine/core";
import { isNotEmpty, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useNavigate } from "react-router";

import { useCustomers } from "@/customers/hooks";
import type { Project } from "@/projects/api";
import { ProjectConflictError, ProjectRuleError } from "@/projects/api";
import { useCreateProject, useUpdateProject } from "@/projects/hooks";

type FormValues = {
  customerId: string;
  name: string;
  description: string;
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
          }
        : { customerId: props.defaultCustomerId ?? "", name: "", description: "" },
    validate: {
      customerId: isNotEmpty("Choose a customer"),
      name: isNotEmpty("Enter a project name"),
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
        const body: { name?: string; description?: string | null } = {};
        if (values.name !== original.name) body.name = values.name;
        const newDescription = values.description || null;
        if (newDescription !== original.description) body.description = newDescription;
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
          <Button type="submit" loading={mutation.isPending} style={{ alignSelf: "flex-start" }}>
            {props.mode === "create" ? "Create project" : "Save changes"}
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
