import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Menu,
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
import type { Customer } from "@/customers/api";
import { CustomerFormModal } from "@/customers/CustomerFormModal";
import { useCustomers, useUpdateCustomer } from "@/customers/hooks";

const PAGE_SIZE = 20;

function billingPeriodLabel(customer: Customer): string {
  const { interval_count: count, interval_unit: unit } = customer.billing_period;
  return `Every ${count} ${unit}${count === 1 ? "" : "s"}`;
}

function CustomerRowActions({ customer }: { customer: Customer }) {
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);
  const [removeOpened, { open: openRemove, close: closeRemove }] = useDisclosure(false);
  const updateCustomer = useUpdateCustomer(customer.id);

  async function handleRestore() {
    await updateCustomer.mutateAsync({ is_active: true });
    notifications.show({ title: "Customer restored", message: customer.name });
  }

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
          {!customer.is_active && (
            <Menu.Item onClick={() => void handleRestore()}>Restore</Menu.Item>
          )}
          <Menu.Divider />
          <Menu.Item color="red" onClick={openRemove}>
            Remove…
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      {editOpened && <CustomerFormModal mode="edit" opened onClose={closeEdit} customer={customer} />}
      <RemoveEntityModal
        entity="customers"
        id={customer.id}
        name={customer.name}
        opened={removeOpened}
        onClose={closeRemove}
      />
    </>
  );
}

export function AdminCustomersPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [page, setPage] = useState(1);
  const [createOpened, { open: openCreate, close: closeCreate }] = useDisclosure(false);

  const customers = useCustomers({
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    includeInactive,
    search: debouncedSearch || undefined,
  });

  function resetToFirstPage() {
    setPage(1);
  }

  const totalPages = customers.data ? Math.ceil(customers.data.total / PAGE_SIZE) : 0;

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Customers</Title>
        <Button onClick={openCreate}>New customer</Button>
      </Group>

      <Group align="flex-end">
        <TextInput
          label="Search"
          placeholder="Name or legal name"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value);
            resetToFirstPage();
          }}
          w={280}
        />
        <Switch
          label="Show archived"
          checked={includeInactive}
          onChange={(event) => {
            setIncludeInactive(event.currentTarget.checked);
            resetToFirstPage();
          }}
          mb={8}
        />
      </Group>

      {customers.isPending && <Loader />}
      {customers.isError && <Alert color="red">Could not load customers.</Alert>}

      {customers.data && (
        <>
          {customers.data.items.length === 0 ? (
            <Text c="dimmed">No customers found.</Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Legal name</Table.Th>
                  <Table.Th>Currency</Table.Th>
                  <Table.Th>Billing period</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {customers.data.items.map((customer) => (
                  <Table.Tr key={customer.id}>
                    <Table.Td>{customer.name}</Table.Td>
                    <Table.Td>{customer.legal_name ?? "—"}</Table.Td>
                    <Table.Td>{customer.currency}</Table.Td>
                    <Table.Td>{billingPeriodLabel(customer)}</Table.Td>
                    <Table.Td>
                      <Badge color={customer.is_active ? "green" : "gray"} variant="light">
                        {customer.is_active ? "Active" : "Archived"}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <CustomerRowActions customer={customer} />
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

      {createOpened && <CustomerFormModal mode="create" opened onClose={closeCreate} />}
    </Stack>
  );
}
