import {
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { canManage, roleLabels } from "@/auth/roles";
import { ProjectFormModal } from "@/projects/ProjectFormModal";
import { ProjectNotFoundError, ProjectRuleError } from "@/projects/api";
import {
  useAddProjectMember,
  useProject,
  useProjectMembers,
  useRemoveProjectMember,
  useUpdateProject,
} from "@/projects/hooks";
import { useUserDirectory } from "@/users/hooks";

function ArchiveButton({ projectId, isActive }: { projectId: string; isActive: boolean }) {
  const [opened, { open, close }] = useDisclosure(false);
  const updateProject = useUpdateProject(projectId);

  async function confirm() {
    try {
      await updateProject.mutateAsync({ is_active: !isActive });
      close();
      notifications.show({
        title: isActive ? "Project archived" : "Project restored",
        message: "",
      });
    } catch (error) {
      if (error instanceof ProjectRuleError) {
        notifications.show({ color: "red", title: "Could not update project", message: error.message });
        close();
      } else {
        throw error;
      }
    }
  }

  return (
    <>
      <Button variant="default" color={isActive ? "red" : undefined} onClick={open}>
        {isActive ? "Archive" : "Restore"}
      </Button>
      <Modal opened={opened} onClose={close} title={isActive ? "Archive project" : "Restore project"}>
        <Stack>
          <Text>
            {isActive
              ? "Archived projects can no longer be re-activated unless their customer is active."
              : "This will make the project active again."}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button color={isActive ? "red" : undefined} loading={updateProject.isPending} onClick={confirm}>
              Confirm
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function RemoveMemberButton({
  projectId,
  userId,
  name,
}: {
  projectId: string;
  userId: string;
  name: string;
}) {
  const [opened, { open, close }] = useDisclosure(false);
  const removeMember = useRemoveProjectMember(projectId);

  async function confirm() {
    await removeMember.mutateAsync(userId);
    close();
    notifications.show({ title: "Member removed", message: name });
  }

  return (
    <>
      <Button variant="subtle" color="red" size="xs" onClick={open}>
        Remove
      </Button>
      <Modal opened={opened} onClose={close} title="Remove member">
        <Stack>
          <Text>
            Remove <strong>{name}</strong> from this project?
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button color="red" loading={removeMember.isPending} onClick={confirm}>
              Remove
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function AddMemberForm({
  projectId,
  isProjectActive,
  memberIds,
}: {
  projectId: string;
  isProjectActive: boolean;
  memberIds: Set<string>;
}) {
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const directory = useUserDirectory(debouncedSearch);
  const addMember = useAddProjectMember(projectId);

  const options = (directory.data ?? [])
    .filter((candidate) => !memberIds.has(candidate.id))
    .map((candidate) => ({ value: candidate.id, label: `${candidate.name} (${candidate.email})` }));

  async function handleAdd() {
    if (!selectedUserId) return;
    try {
      await addMember.mutateAsync(selectedUserId);
      setSelectedUserId(null);
      setSearch("");
      notifications.show({ title: "Member added", message: "" });
    } catch (error) {
      if (error instanceof ProjectRuleError) {
        notifications.show({ color: "red", title: "Could not add member", message: error.message });
      } else {
        throw error;
      }
    }
  }

  return (
    <Group align="flex-end">
      <Select
        label="Add a member"
        placeholder="Search by name or email"
        searchable
        searchValue={search}
        onSearchChange={setSearch}
        data={options}
        value={selectedUserId}
        onChange={setSelectedUserId}
        disabled={!isProjectActive}
        w={320}
      />
      <Button
        onClick={handleAdd}
        disabled={!selectedUserId || !isProjectActive}
        loading={addMember.isPending}
      >
        Add
      </Button>
      {!isProjectActive && (
        <Text c="dimmed" size="sm">
          Restore the project to add members.
        </Text>
      )}
    </Group>
  );
}

export function ProjectDetailsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const user = useAuthenticatedUser();
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);

  const project = useProject(projectId ?? "");
  const members = useProjectMembers(projectId ?? "");

  if (project.isPending) return <Loader />;

  if (project.isError) {
    if (project.error instanceof ProjectNotFoundError) {
      return (
        <Stack>
          <Title order={2}>Project not found</Title>
          <Anchor component={Link} to="/projects">
            Back to projects
          </Anchor>
        </Stack>
      );
    }
    return <Alert color="red">Could not load the project.</Alert>;
  }

  const data = project.data;
  const memberIds = new Set((members.data ?? []).map((member) => member.user_id));

  return (
    <Stack>
      <Group justify="space-between">
        <div>
          <Group gap="sm">
            <Title order={2}>{data.name}</Title>
            <Badge color={data.is_active ? "green" : "gray"} variant="light">
              {data.is_active ? "Active" : "Archived"}
            </Badge>
          </Group>
          <Text c="dimmed">{data.customer.name}</Text>
        </div>
        {canManage(user.role) && (
          <Group>
            <Button variant="default" onClick={openEdit}>
              Edit
            </Button>
            <ArchiveButton projectId={data.id} isActive={data.is_active} />
          </Group>
        )}
      </Group>

      {data.description && <Text>{data.description}</Text>}

      <Title order={3} mt="md">
        Members
      </Title>
      {members.isPending && <Loader />}
      {members.isError && <Alert color="red">Could not load members.</Alert>}
      {members.data && (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Email</Table.Th>
              <Table.Th>Role</Table.Th>
              {canManage(user.role) && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {members.data.map((member) => (
              <Table.Tr key={member.user_id}>
                <Table.Td>
                  {member.name}
                  {!member.is_active && (
                    <Badge ml="xs" size="xs" color="gray" variant="light">
                      Inactive
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>{member.email}</Table.Td>
                <Table.Td>{roleLabels[member.role]}</Table.Td>
                {canManage(user.role) && (
                  <Table.Td>
                    <RemoveMemberButton
                      projectId={data.id}
                      userId={member.user_id}
                      name={member.name}
                    />
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {canManage(user.role) && (
        <AddMemberForm projectId={data.id} isProjectActive={data.is_active} memberIds={memberIds} />
      )}

      {editOpened && <ProjectFormModal mode="edit" opened project={data} onClose={closeEdit} />}
    </Stack>
  );
}
