import { Anchor, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <Stack>
      <Title order={2}>Page not found</Title>
      <Text>
        <Anchor component={Link} to="/">
          Back to home
        </Anchor>
      </Text>
    </Stack>
  );
}
