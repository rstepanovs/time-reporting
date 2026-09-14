import {
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Loader,
  Menu,
  Modal,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { canManage, isAdmin, roleLabels } from "@/auth/roles";
import { BillingItemFormModal, formatBillingItemPrice } from "@/projects/BillingItemFormModal";
import { ProjectFormModal } from "@/projects/ProjectFormModal";
import {
  type BillingItem,
  BillingItemInUseError,
  type Project,
  ProjectNotFoundError,
  ProjectRuleError,
} from "@/projects/api";
import {
  useAddProjectMember,
  useDeleteProjectBillingItem,
  useProject,
  useProjectBillingItems,
  useProjectMembers,
  useRemoveProjectMember,
  useUpdateProject,
  useUpdateProjectBillingItem,
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

function ArchiveBillingItemAction({
  projectId,
  item,
}: {
  projectId: string;
  item: BillingItem;
}) {
  const updateItem = useUpdateProjectBillingItem(projectId);

  async function handleClick() {
    try {
      await updateItem.mutateAsync({ itemId: item.id, body: { is_active: !item.is_active } });
      notifications.show({
        title: item.is_active ? "Billing item archived" : "Billing item restored",
        message: item.name,
      });
    } catch (error) {
      if (error instanceof ProjectRuleError) {
        notifications.show({
          color: "red",
          title: "Could not update billing item",
          message: error.message,
        });
      } else {
        throw error;
      }
    }
  }

  return (
    <Menu.Item onClick={() => void handleClick()}>
      {item.is_active ? "Archive" : "Restore"}
    </Menu.Item>
  );
}

function DeleteBillingItemModal({
  projectId,
  item,
  opened,
  onClose,
}: {
  projectId: string;
  item: BillingItem;
  opened: boolean;
  onClose: () => void;
}) {
  const deleteItem = useDeleteProjectBillingItem(projectId);
  const [blockedReason, setBlockedReason] = useState<string | null>(null);

  function handleClose() {
    setBlockedReason(null);
    onClose();
  }

  async function confirm() {
    setBlockedReason(null);
    try {
      await deleteItem.mutateAsync(item.id);
      handleClose();
      notifications.show({ title: "Billing item deleted", message: item.name });
    } catch (error) {
      if (error instanceof BillingItemInUseError) {
        setBlockedReason(error.message);
        return;
      }
      throw error;
    }
  }

  return (
    <Modal opened={opened} onClose={handleClose} title="Delete billing item">
      <Stack>
        <Text>
          Permanently delete <strong>{item.name}</strong>? This cannot be undone.
        </Text>
        {blockedReason && (
          <Alert color="yellow" variant="light">
            {blockedReason}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={handleClose}>
            Cancel
          </Button>
          <Button color="red" loading={deleteItem.isPending} onClick={() => void confirm()}>
            Delete permanently
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function BillingItemRowActions({
  projectId,
  currency,
  item,
  canDeletePermanently,
}: {
  projectId: string;
  currency: string;
  item: BillingItem;
  canDeletePermanently: boolean;
}) {
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);
  // The delete confirmation lives outside <Menu.Dropdown>, like the edit modal above: Mantine
  // closes (and unmounts) the dropdown as soon as a Menu.Item is clicked, which would tear this
  // component down — and its "opened" state with it — before the modal ever got to render.
  const [deleteOpened, { open: openDelete, close: closeDelete }] = useDisclosure(false);

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
          <ArchiveBillingItemAction projectId={projectId} item={item} />
          {canDeletePermanently && (
            <>
              <Menu.Divider />
              <Menu.Item color="red" onClick={openDelete}>
                Delete permanently…
              </Menu.Item>
            </>
          )}
        </Menu.Dropdown>
      </Menu>
      {editOpened && (
        <BillingItemFormModal
          mode="edit"
          opened
          onClose={closeEdit}
          projectId={projectId}
          currency={currency}
          item={item}
        />
      )}
      {deleteOpened && (
        <DeleteBillingItemModal
          projectId={projectId}
          item={item}
          opened
          onClose={closeDelete}
        />
      )}
    </>
  );
}

function BillingItemsSection({
  project,
  isManager,
  canDeletePermanently,
}: {
  project: Project;
  isManager: boolean;
  canDeletePermanently: boolean;
}) {
  const [showArchived, setShowArchived] = useState(false);
  const [addOpened, { open: openAdd, close: closeAdd }] = useDisclosure(false);
  const billingItems = useProjectBillingItems(project.id, showArchived);

  return (
    <>
      <Group justify="space-between" mt="md">
        <Title order={3}>Billing items</Title>
        <Group>
          <Switch
            label="Show archived"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.currentTarget.checked)}
          />
          {isManager && (
            <Button variant="default" onClick={openAdd} disabled={!project.is_active}>
              Add billing item
            </Button>
          )}
        </Group>
      </Group>
      {isManager && !project.is_active && (
        <Text c="dimmed" size="sm">
          Restore the project to add billing items.
        </Text>
      )}

      {billingItems.isPending && <Loader />}
      {billingItems.isError && <Alert color="red">Could not load billing items.</Alert>}
      {billingItems.data && (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Unit</Table.Th>
              <Table.Th>Price</Table.Th>
              {isManager && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {billingItems.data.map((item) => (
              <Table.Tr key={item.id}>
                <Table.Td>
                  {item.name}
                  {item.preset !== null && (
                    <Badge ml="xs" size="xs" variant="light">
                      Default
                    </Badge>
                  )}
                  {!item.is_active && (
                    <Badge ml="xs" size="xs" color="gray" variant="light">
                      Archived
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td style={{ textTransform: "capitalize" }}>{item.unit}</Table.Td>
                <Table.Td>{formatBillingItemPrice(item, project.customer.currency)}</Table.Td>
                {isManager && (
                  <Table.Td>
                    <BillingItemRowActions
                      projectId={project.id}
                      currency={project.customer.currency}
                      item={item}
                      canDeletePermanently={canDeletePermanently}
                    />
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {addOpened && (
        <BillingItemFormModal
          mode="create"
          opened
          onClose={closeAdd}
          projectId={project.id}
          currency={project.customer.currency}
        />
      )}
    </>
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

      <BillingItemsSection
        project={data}
        isManager={canManage(user.role)}
        canDeletePermanently={isAdmin(user.role)}
      />

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
