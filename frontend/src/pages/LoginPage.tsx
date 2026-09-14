import { Alert, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { isNotEmpty, useForm } from "@mantine/form";
import { Navigate, useLocation } from "react-router";

import { InvalidCredentialsError, SessionNotStoredError } from "@/auth/api";
import { useCurrentUser, useSignIn } from "@/auth/hooks";
import { redirectTarget } from "@/auth/redirect";
import { FullPageLoader } from "@/components/FullPageLoader";

function signInErrorMessage(error: Error): string {
  if (error instanceof InvalidCredentialsError || error instanceof SessionNotStoredError) {
    return error.message;
  }
  return "Could not sign in. Please try again later.";
}

export function LoginPage() {
  const location = useLocation();
  const currentUser = useCurrentUser();
  const signIn = useSignIn();
  const form = useForm({
    mode: "uncontrolled",
    initialValues: { email: "", password: "" },
    validate: {
      email: isNotEmpty("Enter your email"),
      password: isNotEmpty("Enter your password"),
    },
  });

  if (currentUser.isPending) return <FullPageLoader />;
  if (currentUser.data) return <Navigate to={redirectTarget(location.state)} replace />;

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder shadow="sm" radius="md" p="xl" w="100%" maw={400}>
        <form noValidate onSubmit={form.onSubmit((values) => signIn.mutate(values))}>
          <Stack>
            <div>
              <Title order={2}>Sign in</Title>
              <Text c="dimmed" size="sm">
                Time Reporting
              </Text>
            </div>
            {signIn.error && (
              <Alert color="red" variant="light">
                {signInErrorMessage(signIn.error)}
              </Alert>
            )}
            <TextInput
              label="Email"
              type="email"
              autoComplete="username"
              required
              data-autofocus
              key={form.key("email")}
              {...form.getInputProps("email")}
            />
            <PasswordInput
              label="Password"
              autoComplete="current-password"
              required
              key={form.key("password")}
              {...form.getInputProps("password")}
            />
            <Button type="submit" loading={signIn.isPending} fullWidth>
              Sign in
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
