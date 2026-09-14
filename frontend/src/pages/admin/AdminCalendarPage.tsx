import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Menu,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { CalendarRuleError, type NonWorkingDay, type NonWorkingDayKind } from "@/calendar/api";
import { useDeleteNonWorkingDay, useImportPublicHolidays, useNonWorkingDays } from "@/calendar/hooks";
import { NON_WORKING_DAY_KIND_LABELS, NonWorkingDayFormModal } from "@/calendar/NonWorkingDayFormModal";
import { todayIso } from "@/timesheets/week";

const KIND_COLOR: Record<NonWorkingDayKind, string> = {
  public_holiday: "orange",
  bridge_day: "yellow",
  company_day_off: "yellow",
};

function weekdayLabel(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, { weekday: "long" });
}

function DeleteDayModal({
  day,
  opened,
  onClose,
}: {
  day: NonWorkingDay;
  opened: boolean;
  onClose: () => void;
}) {
  const deleteDay = useDeleteNonWorkingDay();

  async function confirm() {
    await deleteDay.mutateAsync(day.id);
    onClose();
    notifications.show({ title: "Non-working day deleted", message: day.name });
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Delete non-working day">
      <Stack>
        <Text>
          Delete <strong>{day.name}</strong> ({day.day})?
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color="red" loading={deleteDay.isPending} onClick={() => void confirm()}>
            Delete
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function DayRowActions({ day }: { day: NonWorkingDay }) {
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);
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
          <Menu.Divider />
          <Menu.Item color="red" onClick={openDelete}>
            Delete
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
      {editOpened && <NonWorkingDayFormModal mode="edit" opened onClose={closeEdit} day={day} />}
      {deleteOpened && <DeleteDayModal day={day} opened onClose={closeDelete} />}
    </>
  );
}

export function AdminCalendarPage() {
  const currentYear = Number(todayIso().slice(0, 4));
  const [year, setYear] = useState(currentYear);
  const [addOpened, { open: openAdd, close: closeAdd }] = useDisclosure(false);
  const days = useNonWorkingDays(year);
  const importHolidays = useImportPublicHolidays();

  async function handleImport() {
    try {
      const added = await importHolidays.mutateAsync(year);
      notifications.show({
        title: "Public holidays imported",
        message: `Added ${added} day${added === 1 ? "" : "s"} for ${year}`,
      });
    } catch (error) {
      if (error instanceof CalendarRuleError) {
        notifications.show({ color: "red", title: "Could not import holidays", message: error.message });
        return;
      }
      throw error;
    }
  }

  const sortedDays = [...(days.data ?? [])].sort((a, b) => a.day.localeCompare(b.day));

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Calendar</Title>
        <Button onClick={openAdd}>Add day</Button>
      </Group>

      <Group align="flex-end">
        <NumberInput
          label="Year"
          value={year}
          onChange={(value) => setYear(value === "" ? currentYear : Number(value))}
          min={1900}
          max={2200}
          hideControls
          w={120}
        />
        <Button variant="default" loading={importHolidays.isPending} onClick={() => void handleImport()}>
          Import public holidays for {year}
        </Button>
      </Group>

      {days.isPending && <Loader />}
      {days.isError && <Alert color="red">Could not load the calendar.</Alert>}

      {days.data && (
        <>
          {sortedDays.length === 0 ? (
            <Text c="dimmed">No non-working days for {year} yet.</Text>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Date</Table.Th>
                  <Table.Th>Weekday</Table.Th>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Kind</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sortedDays.map((day) => (
                  <Table.Tr key={day.id}>
                    <Table.Td>{day.day}</Table.Td>
                    <Table.Td>{weekdayLabel(day.day)}</Table.Td>
                    <Table.Td>{day.name}</Table.Td>
                    <Table.Td>
                      <Badge color={KIND_COLOR[day.kind]} variant="light">
                        {NON_WORKING_DAY_KIND_LABELS[day.kind]}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <DayRowActions day={day} />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </>
      )}

      {addOpened && <NonWorkingDayFormModal mode="create" opened onClose={closeAdd} />}
    </Stack>
  );
}
