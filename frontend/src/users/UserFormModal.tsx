import { Alert, Button, Checkbox, Modal, PasswordInput, Stack, TextInput } from "@mantine/core";
import { hasLength, isEmail, isNotEmpty, useForm } from "@mantine/form";

import { useAuthenticatedUser } from "@/auth/hooks";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from "@/auth/passwords";
import { roleLabels } from "@/auth/roles";
import type { User, UserRole } from "@/users/api";
import { UserEmailConflictError, UserRuleError } from "@/users/api";
import { useCreateUser, useUpdateUser } from "@/users/hooks";

const ROLE_OPTIONS: { value: UserRole; description: string }[] = [
  {
    value: "admin",
    description:
      "System administration only: users, calendar, permanent deletion, system status, " +
      "reopening billing periods.",
  },
  {
    value: "manager",
    description:
      "Customers, projects, members, billing items, approvals, team overview, sending to " +
      "billing.",
  },
  {
    value: "accountant",
    description: "A flag only for now; real permissions arrive with the invoices module.",
  },
];

function sameRoles(a: UserRole[], b: UserRole[]): boolean {
  if (a.length !== b.length) return false;
  const bSet = new Set(b);
  return a.every((role) => bSet.has(role));
}

type FormValues = {
  name: string;
  email: string;
  roles: UserRole[];
  password: string;
};

type Props =
  | { mode: "create"; opened: boolean; onClose: () => void }
  | { mode: "edit"; opened: boolean; onClose: () => void; user: User };

export function UserFormModal(props: Props) {
  const { opened, onClose } = props;
  const currentUser = useAuthenticatedUser();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser(props.mode === "edit" ? props.user.id : "");
  const isSelf = props.mode === "edit" && props.user.id === currentUser.id;

  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues:
      props.mode === "edit"
        ? {
            name: props.user.name,
            email: props.user.email,
            roles: props.user.roles,
            password: "",
          }
        : { name: "", email: "", roles: [], password: "" },
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
          roles: values.roles,
          password: values.password,
        });
      } else {
        const original = props.user;
        const body: { name?: string; email?: string; roles?: UserRole[] } = {};
        if (values.name !== original.name) body.name = values.name;
        if (values.email !== original.email) body.email = values.email;
        if (!sameRoles(values.roles, original.roles)) body.roles = values.roles;
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
          <Checkbox.Group
            label="Access levels"
            description="Every user is an employee and reports time, regardless of these levels."
            key={form.key("roles")}
            {...form.getInputProps("roles")}
          >
            <Stack gap="xs" mt="xs">
              {ROLE_OPTIONS.map((option) => (
                <Checkbox
                  key={option.value}
                  value={option.value}
                  label={roleLabels[option.value]}
                  description={option.description}
                  disabled={isSelf && option.value === "admin"}
                />
              ))}
            </Stack>
          </Checkbox.Group>
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
