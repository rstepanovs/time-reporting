import { Button, Group, Modal, Select, Stack } from "@mantine/core";
import { useState } from "react";

import type { PickedRow } from "@/timesheets/api";
import { useTimesheetOptions } from "@/timesheets/hooks";

type Props = {
  opened: boolean;
  onClose: () => void;
  /** Billing item ids already shown in the grid (server rows plus already-added draft rows). */
  excludeBillingItemIds: Set<string>;
  onAdd: (row: PickedRow) => void;
};

/** Pick a project, then one of its billing items not already shown, and add it as a draft row —
 * it isn't saved until a value is entered and "Save" is pressed. */
export function AddRowModal({ opened, onClose, excludeBillingItemIds, onAdd }: Props) {
  const options = useTimesheetOptions();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [billingItemId, setBillingItemId] = useState<string | null>(null);

  function handleClose() {
    setProjectId(null);
    setBillingItemId(null);
    onClose();
  }

  const projectOptions = (options.data ?? []).map((option) => ({
    value: option.project.id,
    label: option.project.name,
  }));
  const selectedOption = options.data?.find((option) => option.project.id === projectId);
  const itemOptions = (selectedOption?.billing_items ?? [])
    .filter((item) => !excludeBillingItemIds.has(item.id))
    .map((item) => ({ value: item.id, label: item.name }));

  function handleAdd() {
    const item = selectedOption?.billing_items.find((candidate) => candidate.id === billingItemId);
    if (!selectedOption || !item) return;
    onAdd({ project: selectedOption.project, billing_item: item });
    handleClose();
  }

  return (
    <Modal opened={opened} onClose={handleClose} title="Add a row">
      <Stack>
        <Select
          label="Project"
          placeholder="Choose a project"
          data={projectOptions}
          value={projectId}
          onChange={(value) => {
            setProjectId(value);
            setBillingItemId(null);
          }}
          disabled={options.isPending}
        />
        <Select
          label="Billing item"
          placeholder={itemOptions.length === 0 ? "No more billing items to add" : "Choose one"}
          data={itemOptions}
          value={billingItemId}
          onChange={setBillingItemId}
          disabled={!projectId}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={handleClose}>
            Cancel
          </Button>
          <Button onClick={handleAdd} disabled={!billingItemId}>
            Add row
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
