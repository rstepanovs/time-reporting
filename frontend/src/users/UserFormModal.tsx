import { Alert, Button, Modal, PasswordInput, Select, Stack, TextInput } from "@mantine/core";
import { hasLength, isEmail, isNotEmpty, useForm } from "@mantine/form";

import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from "@/auth/passwords";
import { EMPLOYEE_LABEL, roleLabels } from "@/auth/roles";
import type { User, UserRole } from "@/users/api";
import { UserEmailConflictError, UserRuleError } from "@/users/api";
import { useCreateUser, useUpdateUser } from "@/users/hooks";

// A plain employee holds no access level, so it isn't a `UserRole` value.
const EMPLOYEE_VALUE = "employee";
const ROLE_OPTIONS = [
  { value: EMPLOYEE_VALUE, label: EMPLOYEE_LABEL },
  ...Object.entries(roleLabels).map(([value, label]) => ({ value, label })),
];

// This single-select is a stand-in for `roles` (a user can hold several levels at once) until
// T5's checkbox group; it can only set/clear one level at a time.
function rolesFromValue(value: string): UserRole[] {
  return value === EMPLOYEE_VALUE ? [] : [value as UserRole];
}

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
        ? {
            name: props.user.name,
            email: props.user.email,
            role: props.user.roles[0] ?? EMPLOYEE_VALUE,
            password: "",
          }
        : { name: "", email: "", role: EMPLOYEE_VALUE, password: "" },
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
          roles: rolesFromValue(values.role),
          password: values.password,
        });
      } else {
        const original = props.user;
        const body: { name?: string; email?: string; roles?: UserRole[] } = {};
        if (values.name !== original.name) body.name = values.name;
        if (values.email !== original.email) body.email = values.email;
        const originalValue = original.roles[0] ?? EMPLOYEE_VALUE;
        if (values.role !== originalValue) body.roles = rolesFromValue(values.role);
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
