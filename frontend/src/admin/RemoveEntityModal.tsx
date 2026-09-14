import { Alert, Button, Checkbox, Group, Loader, Modal, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  type RemovableEntity,
  RemovalBlockedError,
  type RemovalCount,
  type RemovalOutcome,
  RemovalRuleError,
} from "@/admin/api";
import { useRemovalImpact, useRemoveEntity } from "@/admin/hooks";

const ENTITY_LABEL: Record<RemovableEntity, string> = {
  users: "user",
  customers: "customer",
  projects: "project",
};

function blockerReason(kind: RemovalCount["kind"], count: number): string {
  switch (kind) {
    case "self":
      return "You cannot delete your own account.";
    case "projects":
      return `Has ${count} project${count === 1 ? "" : "s"}. Delete or reassign them first.`;
    default:
      return "This record is referenced by other data.";
  }
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function effectPhrase(kind: RemovalCount["kind"], count: number): string {
  switch (kind) {
    case "project_memberships":
      return `${count} project membership${count === 1 ? "" : "s"}`;
    case "project_members":
      return `${count} project member${count === 1 ? "" : "s"}`;
    case "project_billing_items":
      return `${count} billing item${count === 1 ? "" : "s"}`;
    default:
      return `${count} related record${count === 1 ? "" : "s"}`;
  }
}

type Props = {
  entity: RemovableEntity;
  id: string;
  name: string;
  opened: boolean;
  onClose: () => void;
  onRemoved?: (outcome: RemovalOutcome) => void;
};

/** Archives `name` by default; a "Delete permanently" checkbox switches to a permanent delete,
 * disabled with a reason when other data still references the record. */
export function RemoveEntityModal({ entity, id, name, opened, onClose, onRemoved }: Props) {
  const [permanentChecked, setPermanentChecked] = useState(false);
  const [serverBlockers, setServerBlockers] = useState<RemovalCount[] | null>(null);
  const impact = useRemovalImpact(entity, id, { enabled: opened });
  const removeEntity = useRemoveEntity(entity);

  const label = ENTITY_LABEL[entity];
  const data = impact.data;
  const alreadyArchived = data?.is_active === false;
  // Once archived, the only thing left to offer is a permanent delete.
  const permanent = alreadyArchived || permanentChecked;
  // A blocker reported by a failed delete (a race with a concurrent insert) takes priority over
  // the impact query's own view, which may not yet reflect it.
  const blockers = serverBlockers ?? data?.blockers ?? [];
  const canDeletePermanently = serverBlockers === null && (data?.can_delete_permanently ?? false);

  function handleClose() {
    setPermanentChecked(false);
    setServerBlockers(null);
    onClose();
  }

  async function handleConfirm() {
    setServerBlockers(null);
    try {
      const outcome = await removeEntity.mutateAsync({ id, permanent });
      notifications.show({
        title: `${capitalize(label)} ${outcome === "deleted" ? "deleted" : "archived"}`,
        message: name,
      });
      onRemoved?.(outcome);
      handleClose();
    } catch (error) {
      if (error instanceof RemovalBlockedError) {
        setServerBlockers(error.blockers);
        await impact.refetch();
        return;
      }
      if (error instanceof RemovalRuleError) {
        notifications.show({ color: "red", title: "Could not remove", message: error.message });
        return;
      }
      throw error;
    }
  }

  return (
    <Modal opened={opened} onClose={handleClose} title={`Remove ${label}`}>
      <Stack>
        {alreadyArchived ? (
          <Text>
            {name} is archived. Permanently deleting it cannot be undone.
          </Text>
        ) : (
          <Text>{name} will be archived by default. It can be restored later.</Text>
        )}

        {impact.isPending && <Loader size="sm" />}

        {data && (
          <>
            {!alreadyArchived && (
              <Checkbox
                label="Delete permanently"
                description="Cannot be undone"
                checked={permanentChecked}
                disabled={!canDeletePermanently}
                onChange={(event) => setPermanentChecked(event.currentTarget.checked)}
              />
            )}

            {!canDeletePermanently && blockers.length > 0 && (
              <Alert color="yellow" variant="light">
                {blockers.map((blocker) => blockerReason(blocker.kind, blocker.count)).join(" ")}
              </Alert>
            )}

            {permanent && data.effects.length > 0 && (
              <Alert color="red" variant="light">
                Also removes {data.effects.map((e) => effectPhrase(e.kind, e.count)).join(", ")}.
                This cannot be undone.
              </Alert>
            )}
          </>
        )}

        <Group justify="flex-end">
          <Button variant="default" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            color={permanent ? "red" : undefined}
            loading={removeEntity.isPending}
            disabled={impact.isPending || (permanent && !canDeletePermanently)}
            onClick={() => void handleConfirm()}
          >
            {permanent ? "Delete permanently" : "Archive"}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
