import {
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Loader,
  Menu,
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
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link } from "react-router";

import { RemoveEntityModal } from "@/admin/RemoveEntityModal";
import { useCustomers } from "@/customers/hooks";
import type { Project } from "@/projects/api";
import { ProjectRuleError } from "@/projects/api";
import { ProjectFormModal } from "@/projects/ProjectFormModal";
import { useProjects, useUpdateProject } from "@/projects/hooks";

const PAGE_SIZE = 20;

function ProjectRowActions({ project }: { project: Project }) {
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);
  const [removeOpened, { open: openRemove, close: closeRemove }] = useDisclosure(false);
  const updateProject = useUpdateProject(project.id);

  async function handleRestore() {
    try {
      await updateProject.mutateAsync({ is_active: true });
      notifications.show({ title: "Project restored", message: project.name });
    } catch (error) {
      if (error instanceof ProjectRuleError) {
        notifications.show({
          color: "red",
          title: "Could not restore project",
          message: error.message,
        });
      } else {
        throw error;
      }
    }
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
          {!project.is_active && (
            <Menu.Item onClick={() => void handleRestore()}>Restore</Menu.Item>
          )}
          <Menu.Divider />
          <Menu.Item color="red" onClick={openRemove}>
            Remove…
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      {editOpened && <ProjectFormModal mode="edit" opened onClose={closeEdit} project={project} />}
      <RemoveEntityModal
        entity="projects"
        id={project.id}
        name={project.name}
        opened={removeOpened}
        onClose={closeRemove}
      />
    </>
  );
}

export function AdminProjectsPage() {
  const customers = useCustomers({ includeInactive: true, limit: 100 });
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [page, setPage] = useState(1);
  const [createOpened, { open: openCreate, close: closeCreate }] = useDisclosure(false);

  const projects = useProjects({
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    includeInactive,
    customerId: customerId ?? undefined,
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
        <Button onClick={openCreate}>New project</Button>
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
                  <Table.Th>Status</Table.Th>
                  <Table.Th />
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
                      <Badge color={project.is_active ? "green" : "gray"} variant="light">
                        {project.is_active ? "Active" : "Archived"}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <ProjectRowActions project={project} />
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

      {createOpened && (
        // Stay on this page after creating a project instead of navigating to its detail page.
        <ProjectFormModal mode="create" opened onClose={closeCreate} onCreated={() => {}} />
      )}
    </Stack>
  );
}
