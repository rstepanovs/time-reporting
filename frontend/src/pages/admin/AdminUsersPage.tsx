import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Menu,
  MultiSelect,
  Pagination,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { RemoveEntityModal } from "@/admin/RemoveEntityModal";
import { useAuthenticatedUser } from "@/auth/hooks";
import { EMPLOYEE_LABEL, roleLabels } from "@/auth/roles";
import { ResetPasswordModal } from "@/users/ResetPasswordModal";
import { type User, type UserRole, UserRuleError } from "@/users/api";
import { useUpdateUser, useUsers } from "@/users/hooks";
import { UserFormModal } from "@/users/UserFormModal";

const PAGE_SIZE = 20;
const ROLE_FILTER_OPTIONS = Object.entries(roleLabels).map(([value, label]) => ({ value, label }));

function AccessLevelBadges({ roles }: { roles: UserRole[] }) {
  if (roles.length === 0) {
    return (
      <Badge color="gray" variant="light">
        {EMPLOYEE_LABEL}
      </Badge>
    );
  }
  return (
    <Group gap={4}>
      {roles.map((role) => (
        <Badge key={role} variant="light">
          {roleLabels[role]}
        </Badge>
      ))}
    </Group>
  );
}

function RestoreAction({ user }: { user: User }) {
  const updateUser = useUpdateUser(user.id);

  async function handleRestore() {
    try {
      await updateUser.mutateAsync({ is_active: true });
      notifications.show({ title: "User restored", message: user.name });
    } catch (error) {
      if (error instanceof UserRuleError) {
        notifications.show({ color: "red", title: "Could not restore user", message: error.message });
      } else {
        throw error;
      }
    }
  }

  return <Menu.Item onClick={() => void handleRestore()}>Restore</Menu.Item>;
}

function UserRowActions({ user, isSelf }: { user: User; isSelf: boolean }) {
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);
  const [resetOpened, { open: openReset, close: closeReset }] = useDisclosure(false);
  const [removeOpened, { open: openRemove, close: closeRemove }] = useDisclosure(false);

  return (
    <>
      <Menu position="bottom-end">
        <Menu.Target>
          <Button variant="subtle" size="xs">
            Actions
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={openEdit}>Edit</Menu.Item>
          <Menu.Item onClick={openReset}>Reset password</Menu.Item>
          {!user.is_active && <RestoreAction user={user} />}
          <Menu.Divider />
          <Menu.Item color="red" disabled={isSelf} onClick={openRemove}>
            Remove…
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      {editOpened && <UserFormModal mode="edit" opened onClose={closeEdit} user={user} />}
      <ResetPasswordModal
        userId={user.id}
        userName={user.name}
        opened={resetOpened}
        onClose={closeReset}
      />
      <RemoveEntityModal
        entity="users"
        id={user.id}
        name={user.name}
        opened={removeOpened}
        onClose={closeRemove}
      />
    </>
  );
}

export function AdminUsersPage() {
  const currentUser = useAuthenticatedUser();
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [includeInactive, setIncludeInactive] = useState(true);
  const [roleFilter, setRoleFilter] = useState<UserRole[]>([]);
  const [page, setPage] = useState(1);
  const [createOpened, { open: openCreate, close: closeCreate }] = useDisclosure(false);

  const users = useUsers({
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    includeInactive,
    search: debouncedSearch || undefined,
    roles: roleFilter.length > 0 ? roleFilter : undefined,
  });

  function resetToFirstPage() {
    setPage(1);
  }

  const totalPages = users.data ? Math.ceil(users.data.total / PAGE_SIZE) : 0;

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Users</Title>
        <Button onClick={openCreate}>New user</Button>
      </Group>

      <Group align="flex-end">
        <TextInput
          label="Search"
          placeholder="Name or email"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value);
            resetToFirstPage();
          }}
          w={280}
        />
        <MultiSelect
          label="Access level"
          placeholder="Any"
          clearable
          data={ROLE_FILTER_OPTIONS}
          value={roleFilter}
          onChange={(value) => {
            setRoleFilter(value as UserRole[]);
            resetToFirstPage();
          }}
          w={280}
        />
        <Switch
          label="Show inactive"
          checked={includeInactive}
          onChange={(event) => {
            setIncludeInactive(event.currentTarget.checked);
            resetToFirstPage();
          }}
          mb={8}
        />
      </Group>

      {users.isPending && <Loader />}
      {users.isError && <Alert color="red">Could not load users.</Alert>}

      {users.data && (
        <>
          {users.data.items.length === 0 ? (
            <Text c="dimmed">No users found.</Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Email</Table.Th>
                  <Table.Th>Access levels</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Last login</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {users.data.items.map((user) => (
                  <Table.Tr key={user.id}>
                    <Table.Td>{user.name}</Table.Td>
                    <Table.Td>{user.email}</Table.Td>
                    <Table.Td>
                      <AccessLevelBadges roles={user.roles} />
                    </Table.Td>
                    <Table.Td>
                      <Badge color={user.is_active ? "green" : "gray"} variant="light">
                        {user.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}
                    </Table.Td>
                    <Table.Td>
                      <UserRowActions user={user} isSelf={user.id === currentUser.id} />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {totalPages > 1 && (
            <Pagination value={page} onChange={setPage} total={totalPages} mt="sm" />
          )}
        </>
      )}

      {createOpened && <UserFormModal mode="create" opened onClose={closeCreate} />}
    </Stack>
  );
}
