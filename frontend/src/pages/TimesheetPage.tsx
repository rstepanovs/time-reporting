import { Alert, Button, Group, Modal, Select, Stack, Text, Title } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { canManage } from "@/auth/roles";
import { TimesheetGrid } from "@/timesheets/TimesheetGrid";
import { addWeeks, formatWeekLabel, startOfIsoWeek, todayIso } from "@/timesheets/week";
import { useUserDirectory } from "@/users/hooks";

type NavIntent = { week?: string; userId?: string };

export function TimesheetPage() {
  const user = useAuthenticatedUser();
  const canPickUser = canManage(user);
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const directory = useUserDirectory(debouncedSearch);
  const [isDirty, setIsDirty] = useState(false);
  const [pendingIntent, setPendingIntent] = useState<NavIntent | null>(null);

  const weekParam = searchParams.get("week");
  const weekStart = startOfIsoWeek(weekParam && /^\d{4}-\d{2}-\d{2}$/.test(weekParam) ? weekParam : todayIso());
  const userParam = searchParams.get("user");
  const selectedUserId = canPickUser && userParam ? userParam : user.id;
  const isOwnWeek = selectedUserId === user.id;

  function applyIntent(intent: NavIntent) {
    const params = new URLSearchParams(searchParams);
    if (intent.week) params.set("week", intent.week);
    if (intent.userId !== undefined) {
      if (intent.userId === user.id) params.delete("user");
      else params.set("user", intent.userId);
    }
    setSearchParams(params);
  }

  function navigate(intent: NavIntent) {
    if (isDirty) {
      setPendingIntent(intent);
      return;
    }
    applyIntent(intent);
  }

  const directoryOptions = [
    { value: user.id, label: `${user.name} (me)` },
    ...(directory.data ?? [])
      .filter((candidate) => candidate.id !== user.id)
      .map((candidate) => ({ value: candidate.id, label: `${candidate.name} (${candidate.email})` })),
  ];

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>Timesheet</Title>
        {canPickUser && (
          <Select
            aria-label="Viewing"
            searchable
            searchValue={search}
            onSearchChange={setSearch}
            data={directoryOptions}
            value={selectedUserId}
            onChange={(value) => navigate({ userId: value ?? user.id })}
            w={280}
            allowDeselect={false}
          />
        )}
      </Group>

      <Group>
        <Button variant="default" onClick={() => navigate({ week: addWeeks(weekStart, -1) })}>
          ← Previous
        </Button>
        <Button variant="default" onClick={() => navigate({ week: startOfIsoWeek(todayIso()) })}>
          This week
        </Button>
        <Button variant="default" onClick={() => navigate({ week: addWeeks(weekStart, 1) })}>
          Next →
        </Button>
        <Text fw={500}>{formatWeekLabel(weekStart)}</Text>
      </Group>

      {!isOwnWeek && (
        <Alert color="blue" variant="light">
          Viewing another user's timesheet — read-only.
        </Alert>
      )}

      <TimesheetGrid
        key={`${selectedUserId}|${weekStart}`}
        userId={selectedUserId}
        weekStart={weekStart}
        onDirtyChange={setIsDirty}
      />

      <Modal
        opened={pendingIntent !== null}
        onClose={() => setPendingIntent(null)}
        title="Discard unsaved changes?"
      >
        <Stack>
          <Text>You have unsaved changes on this week. Leaving now will discard them.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPendingIntent(null)}>
              Cancel
            </Button>
            <Button
              color="red"
              onClick={() => {
                if (pendingIntent) applyIntent(pendingIntent);
                setPendingIntent(null);
              }}
            >
              Discard and continue
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
