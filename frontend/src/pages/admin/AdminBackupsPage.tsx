import { Alert, Anchor, Button, Group, Loader, Stack, Table, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";

import { BackupFailedError, BackupInProgressError, backupDownloadUrl } from "@/system/api";
import { formatBytes } from "@/system/format";
import { useBackups, useCreateBackup } from "@/system/hooks";

export function AdminBackupsPage() {
  const backups = useBackups();
  const createBackup = useCreateBackup();

  async function handleCreate() {
    try {
      const backup = await createBackup.mutateAsync();
      notifications.show({ title: "Backup created", message: backup.name });
    } catch (error) {
      if (error instanceof BackupInProgressError) {
        notifications.show({ color: "red", title: "Backup already running", message: error.message });
        return;
      }
      if (error instanceof BackupFailedError) {
        notifications.show({ color: "red", title: "Backup failed", message: error.message });
        return;
      }
      throw error;
    }
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Backups</Title>
        <Button loading={createBackup.isPending} onClick={() => void handleCreate()}>
          Create backup now
        </Button>
      </Group>

      <Text size="sm" c="dimmed">
        Restoring from a backup is a CLI-only operation (<code>time-reporting restore &lt;file&gt;
        --yes</code>), not available from this page.
      </Text>

      {backups.isPending && <Loader />}
      {backups.isError && <Alert color="red">Could not load backups.</Alert>}

      {backups.data &&
        (backups.data.backups.length === 0 ? (
          <Text c="dimmed">No backups yet.</Text>
        ) : (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>File name</Table.Th>
                <Table.Th>Created</Table.Th>
                <Table.Th>Size</Table.Th>
                <Table.Th>Revision</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {backups.data.backups.map((backup) => (
                <Table.Tr key={backup.name}>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {backup.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>{new Date(backup.created_at).toLocaleString()}</Table.Td>
                  <Table.Td>{formatBytes(backup.size_bytes)}</Table.Td>
                  <Table.Td>{backup.revision ?? "unknown"}</Table.Td>
                  <Table.Td>
                    <Anchor href={backupDownloadUrl(backup.name)} download>
                      Download
                    </Anchor>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ))}
    </Stack>
  );
}
