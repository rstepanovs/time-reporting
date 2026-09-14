import { Alert, Button, Paper, PasswordInput, Stack, Text, Title } from "@mantine/core";
import { hasLength, isNotEmpty, matchesField, useForm } from "@mantine/form";

import { InvalidCurrentPasswordError } from "@/auth/api";
import { useChangePassword } from "@/auth/hooks";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from "@/auth/passwords";

export function ChangePasswordPage() {
  const changePassword = useChangePassword();
  const form = useForm({
    mode: "uncontrolled",
    initialValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
    validate: {
      currentPassword: isNotEmpty("Enter your current password"),
      newPassword: hasLength(
        { min: PASSWORD_MIN_LENGTH, max: PASSWORD_MAX_LENGTH },
        `Use ${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters`,
      ),
      confirmPassword: matchesField("newPassword", "Passwords do not match"),
    },
  });

  const handleSubmit = form.onSubmit(async ({ currentPassword, newPassword }) => {
    try {
      await changePassword.mutateAsync({ currentPassword, newPassword });
    } catch (error) {
      if (error instanceof InvalidCurrentPasswordError) {
        form.setFieldError("currentPassword", error.message);
      }
    }
  });

  const unexpectedError =
    changePassword.error && !(changePassword.error instanceof InvalidCurrentPasswordError);

  return (
    <Stack maw={420}>
      <div>
        <Title order={2}>Change password</Title>
        <Text c="dimmed" size="sm">
          You will be signed out and asked to sign in with the new password.
        </Text>
      </div>
      <Paper withBorder p="lg">
        <form noValidate onSubmit={handleSubmit}>
          <Stack>
            {unexpectedError && (
              <Alert color="red" variant="light">
                Could not change the password. Please try again later.
              </Alert>
            )}
            <PasswordInput
              label="Current password"
              autoComplete="current-password"
              required
              key={form.key("currentPassword")}
              {...form.getInputProps("currentPassword")}
            />
            <PasswordInput
              label="New password"
              description={`${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters`}
              autoComplete="new-password"
              required
              key={form.key("newPassword")}
              {...form.getInputProps("newPassword")}
            />
            <PasswordInput
              label="Confirm new password"
              autoComplete="new-password"
              required
              key={form.key("confirmPassword")}
              {...form.getInputProps("confirmPassword")}
            />
            <Button type="submit" loading={changePassword.isPending} style={{ alignSelf: "flex-start" }}>
              Change password
            </Button>
          </Stack>
        </form>
      </Paper>
    </Stack>
  );
}
