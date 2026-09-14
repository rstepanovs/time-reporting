import { Button, Modal, PasswordInput, Stack, Text } from "@mantine/core";
import { hasLength, matchesField, useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";

import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from "@/auth/passwords";
import { useResetUserPassword } from "@/users/hooks";

type FormValues = { newPassword: string; confirmPassword: string };

export function ResetPasswordModal({
  userId,
  userName,
  opened,
  onClose,
}: {
  userId: string;
  userName: string;
  opened: boolean;
  onClose: () => void;
}) {
  const resetPassword = useResetUserPassword(userId);
  const form = useForm<FormValues>({
    mode: "uncontrolled",
    initialValues: { newPassword: "", confirmPassword: "" },
    validate: {
      newPassword: hasLength(
        { min: PASSWORD_MIN_LENGTH, max: PASSWORD_MAX_LENGTH },
        `Use ${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters`,
      ),
      confirmPassword: matchesField("newPassword", "Passwords do not match"),
    },
  });

  const handleSubmit = form.onSubmit(async ({ newPassword }) => {
    await resetPassword.mutateAsync(newPassword);
    notifications.show({ title: "Password reset", message: userName });
    form.reset();
    onClose();
  });

  return (
    <Modal opened={opened} onClose={onClose} title="Reset password">
      <form noValidate onSubmit={handleSubmit}>
        <Stack>
          <Text size="sm" c="dimmed">
            {userName} will be signed out of every session and must sign in with the new password.
          </Text>
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
          <Button type="submit" loading={resetPassword.isPending} style={{ alignSelf: "flex-start" }}>
            Reset password
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
