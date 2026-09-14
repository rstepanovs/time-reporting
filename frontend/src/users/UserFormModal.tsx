import { Alert, Button, Modal, PasswordInput, Select, Stack, TextInput } from "@mantine/core";
import { hasLength, isEmail, isNotEmpty, useForm } from "@mantine/form";

import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from "@/auth/passwords";
import { roleLabels } from "@/auth/roles";
import type { User } from "@/users/api";
import { UserEmailConflictError, UserRuleError } from "@/users/api";
import { useCreateUser, useUpdateUser } from "@/users/hooks";

const ROLE_OPTIONS = Object.entries(roleLabels).map(([value, label]) => ({ value, label }));

type FormValues = {
  name: string;
  email: string;
  role: string;
  password: string;
};

type Props =
  | { mode: "create"; opened: boolean; onClose: () => void }
  | { mode: "edit"; opened: boolean; onClose: () => void; user: User };

export function UserFormModal(props: Props) {
  const { opened, onClose } = props;
  const createUser = useCreateUser();
  const updateUser = useUpdateUser(props.mode === "edit" ? props.user.id : "");

  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues:
      props.mode === "edit"
        ? { name: props.user.name, email: props.user.email, role: props.user.role, password: "" }
        : { name: "", email: "", role: "worker", password: "" },
    validate: {
      name: isNotEmpty("Enter a name"),
      email: isEmail("Enter a valid email"),
      password:
        props.mode === "create"
          ? hasLength(
              { min: PASSWORD_MIN_LENGTH, max: PASSWORD_MAX_LENGTH },
              `Use ${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters`,
            )
          : undefined,
    },
  });

  const mutation = props.mode === "create" ? createUser : updateUser;

  const handleSubmit = form.onSubmit(async (values) => {
    try {
      if (props.mode === "create") {
        await createUser.mutateAsync({
          name: values.name,
          email: values.email,
          role: values.role as User["role"],
          password: values.password,
        });
      } else {
        const original = props.user;
        const body: { name?: string; email?: string; role?: User["role"] } = {};
        if (values.name !== original.name) body.name = values.name;
        if (values.email !== original.email) body.email = values.email;
        if (values.role !== original.role) body.role = values.role as User["role"];
        await updateUser.mutateAsync(body);
      }
      onClose();
    } catch (error) {
      if (error instanceof UserEmailConflictError) {
        form.setFieldError("email", error.message);
      } else if (!(error instanceof UserRuleError)) {
        throw error;
      }
    }
  });

  const ruleError = mutation.error instanceof UserRuleError ? mutation.error : null;

  return (
    <Modal opened={opened} onClose={onClose} title={props.mode === "create" ? "New user" : "Edit user"}>
      <form noValidate onSubmit={handleSubmit}>
        <Stack>
          {ruleError && (
            <Alert color="red" variant="light">
              {ruleError.message}
            </Alert>
          )}
          <TextInput
            label="Name"
            required
            maxLength={255}
            key={form.key("name")}
            {...form.getInputProps("name")}
          />
          <TextInput
            label="Email"
            type="email"
            required
            key={form.key("email")}
            {...form.getInputProps("email")}
          />
          <Select
            label="Role"
            required
            data={ROLE_OPTIONS}
            allowDeselect={false}
            key={form.key("role")}
            {...form.getInputProps("role")}
          />
          {props.mode === "create" && (
            <PasswordInput
              label="Password"
              description={`${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters`}
              autoComplete="new-password"
              required
              key={form.key("password")}
              {...form.getInputProps("password")}
            />
          )}
          <Button type="submit" loading={mutation.isPending} style={{ alignSelf: "flex-start" }}>
            {props.mode === "create" ? "Create user" : "Save changes"}
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
