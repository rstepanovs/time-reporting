import {
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { useState } from "react";
import { Link } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { canManage } from "@/auth/roles";
import { useCustomers } from "@/customers/hooks";
import { ProjectFormModal } from "@/projects/ProjectFormModal";
import { useProjects } from "@/projects/hooks";

const PAGE_SIZE = 20;

export function ProjectsPage() {
  const user = useAuthenticatedUser();
  const customers = useCustomers({ includeInactive: true, limit: 100 });
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [managedByMe, setManagedByMe] = useState(false);
  const [page, setPage] = useState(1);
  const [createOpened, { open: openCreate, close: closeCreate }] = useDisclosure(false);

  const projects = useProjects({
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    includeInactive,
    customerId: customerId ?? undefined,
    managerId: managedByMe ? user.id : undefined,
    search: debouncedSearch || undefined,
  });

  function resetToFirstPage() {
    setPage(1);
  }

  const totalPages = projects.data ? Math.ceil(projects.data.total / PAGE_SIZE) : 0;

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Projects</Title>
        {canManage(user.role) && <Button onClick={openCreate}>New project</Button>}
      </Group>

      <Group align="flex-end">
        <Select
          label="Customer"
          placeholder="All customers"
          clearable
          searchable
          data={(customers.data?.items ?? []).map((customer) => ({
            value: customer.id,
            label: customer.name,
          }))}
          value={customerId}
          onChange={(value) => {
            setCustomerId(value);
            resetToFirstPage();
          }}
          w={220}
        />
        <TextInput
          label="Search"
          placeholder="Project name"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value);
            resetToFirstPage();
          }}
          w={220}
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
        {canManage(user.role) && (
          <Switch
            label="Managed by me"
            checked={managedByMe}
            onChange={(event) => {
              setManagedByMe(event.currentTarget.checked);
              resetToFirstPage();
            }}
            mb={8}
          />
        )}
      </Group>

      {projects.isPending && <Loader />}
      {projects.isError && <Alert color="red">Could not load projects.</Alert>}

      {projects.data && (
        <>
          {projects.data.items.length === 0 ? (
            <Text c="dimmed">No projects found.</Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Customer</Table.Th>
                  <Table.Th>Manager</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {projects.data.items.map((project) => (
                  <Table.Tr key={project.id}>
                    <Table.Td>
                      <Anchor component={Link} to={`/projects/${project.id}`}>
                        {project.name}
                      </Anchor>
                    </Table.Td>
                    <Table.Td>{project.customer.name}</Table.Td>
                    <Table.Td>
                      {project.manager ? (
                        project.manager.name
                      ) : (
                        <Text c="dimmed" span>
                          None
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Badge color={project.is_active ? "green" : "gray"} variant="light">
                        {project.is_active ? "Active" : "Archived"}
                      </Badge>
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

      {createOpened && <ProjectFormModal mode="create" opened onClose={closeCreate} />}
    </Stack>
  );
}
