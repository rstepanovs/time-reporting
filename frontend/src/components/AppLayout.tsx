import {
  AppShell,
  Avatar,
  Badge,
  Box,
  Burger,
  Group,
  Menu,
  NavLink,
  Text,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Link, Outlet, useLocation } from "react-router";

import { useAuthenticatedUser, useSignOut } from "@/auth/hooks";
import { EMPLOYEE_LABEL, canManage, isAdmin, roleLabels } from "@/auth/roles";

function AccountMenu() {
  const user = useAuthenticatedUser();
  const signOut = useSignOut();
  const levelLabels =
    user.roles.length > 0 ? user.roles.map((role) => roleLabels[role]) : [EMPLOYEE_LABEL];

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
          <Group gap={4} mt={6}>
            {levelLabels.map((label) => (
              <Badge key={label} size="xs" variant="light">
                {label}
              </Badge>
            ))}
          </Group>
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

const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/timesheet", label: "Timesheet" },
  { to: "/hours", label: "My hours" },
  { to: "/projects", label: "Projects" },
];

// Shown only to managers, right after "My hours".
const APPROVALS_NAV_ITEM = { to: "/approvals", label: "Approvals" };
const TEAM_NAV_ITEM = { to: "/team", label: "Team" };

const ADMIN_NAV_ITEMS = [
  { to: "/admin/users", label: "Users" },
  { to: "/admin/customers", label: "Customers" },
  { to: "/admin/projects", label: "Projects" },
  { to: "/admin/calendar", label: "Calendar" },
  { to: "/admin/backups", label: "Backups" },
  { to: "/admin/status", label: "System status" },
];

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation();
  const user = useAuthenticatedUser();
  const navItems = canManage(user)
    ? [...NAV_ITEMS.slice(0, 3), APPROVALS_NAV_ITEM, TEAM_NAV_ITEM, ...NAV_ITEMS.slice(3)]
    : NAV_ITEMS;

  return (
    <>
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          component={Link}
          to={item.to}
          label={item.label}
          active={
            item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)
          }
          onClick={onNavigate}
        />
      ))}
      {isAdmin(user) && (
        <NavLink
          label="Administration"
          defaultOpened={location.pathname.startsWith("/admin")}
        >
          {ADMIN_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              component={Link}
              to={item.to}
              label={item.label}
              active={location.pathname.startsWith(item.to)}
              onClick={onNavigate}
            />
          ))}
        </NavLink>
      )}
    </>
  );
}

export function AppLayout() {
  const [mobileOpened, { toggle: toggleMobile, close: closeMobile }] = useDisclosure();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !mobileOpened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={mobileOpened} onClick={toggleMobile} hiddenFrom="sm" size="sm" />
            <Title order={3}>Time Reporting</Title>
          </Group>
          <AccountMenu />
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <Navigation onNavigate={closeMobile} />
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
