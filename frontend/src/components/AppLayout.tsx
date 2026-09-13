import { AppShell, Avatar, Badge, Box, Group, Menu, Text, Title, UnstyledButton } from "@mantine/core";
import { Link, Outlet } from "react-router";

import { useAuthenticatedUser, useSignOut } from "@/auth/hooks";
import { roleLabels } from "@/auth/roles";

function AccountMenu() {
  const user = useAuthenticatedUser();
  const signOut = useSignOut();

  return (
    <Menu position="bottom-end" width={260}>
      <Menu.Target>
        <UnstyledButton aria-label="Account menu">
          <Group gap="xs">
            <Avatar name={user.name} color="initials" size="sm" />
            <Text size="sm" fw={500} visibleFrom="xs">
              {user.name}
            </Text>
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Box px="sm" py="xs">
          <Text size="sm" fw={500}>
            {user.name}
          </Text>
          <Text size="xs" c="dimmed">
            {user.email}
          </Text>
          <Badge size="xs" variant="light" mt={6}>
            {roleLabels[user.role]}
          </Badge>
        </Box>
        <Menu.Divider />
        <Menu.Item component={Link} to="/account/password">
          Change password
        </Menu.Item>
        <Menu.Item color="red" disabled={signOut.isPending} onClick={() => signOut.mutate()}>
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

export function AppLayout() {
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={3}>Time Reporting</Title>
          <AccountMenu />
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
