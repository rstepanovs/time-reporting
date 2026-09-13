import { Button, Center, Stack, Text } from "@mantine/core";
import { Navigate, Outlet, useLocation } from "react-router";

import { useCurrentUser } from "@/auth/hooks";
import { signInRedirectState } from "@/auth/redirect";
import { FullPageLoader } from "@/components/FullPageLoader";

/** Renders child routes only for a signed-in user; everyone else is sent to the sign-in page. */
export function RequireAuth() {
  const location = useLocation();
  const { data: user, error, refetch, isFetching } = useCurrentUser();

  if (user === undefined) {
    if (!error) return <FullPageLoader />;
    return (
      <Center mih="100vh" p="md">
        <Stack align="center">
          <Text>Could not reach the server.</Text>
          <Button onClick={() => void refetch()} loading={isFetching}>
            Retry
          </Button>
        </Stack>
      </Center>
    );
  }
  if (user === null) {
    return <Navigate to="/login" replace state={signInRedirectState(location)} />;
  }
  return <Outlet />;
}
