import { Alert, Badge, Card, Group, Loader, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { SystemStatus } from "@/system/api";
import { useSystemConfig, useSystemStatus } from "@/system/hooks";

const POLL_INTERVAL_MS = 10_000;

function useProbe(key: string, request: () => Promise<{ response: Response }>) {
  return useQuery({
    queryKey: ["health", key],
    queryFn: async () => (await request()).response.ok,
    refetchInterval: POLL_INTERVAL_MS,
    retry: false,
  });
}

function probeBadge(probe: UseQueryResult<boolean>): { color: string; label: string } {
  if (probe.isPending) return { color: "gray", label: "checking" };
  if (probe.data) return { color: "green", label: "ok" };
  return { color: "red", label: "unavailable" };
}

function ProbeRow({ name, probe }: { name: string; probe: UseQueryResult<boolean> }) {
  const { color, label } = probeBadge(probe);
  return (
    <Group justify="space-between">
      <Text>{name}</Text>
      <Badge color={color}>{label}</Badge>
    </Group>
  );
}

function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (days > 0 || hours > 0) parts.push(`${hours}h`);
  parts.push(`${minutes}m`);
  return parts.join(" ");
}

function shortSha(sha: string | null): string {
  return sha ? sha.slice(0, 12) : "unknown";
}

function VersionsCard({ status }: { status: SystemStatus }) {
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={500}>Versions</Text>
        <Group justify="space-between">
          <Text>Backend</Text>
          <Text c="dimmed">
            {status.backend_version} ({shortSha(status.git_sha)})
          </Text>
        </Group>
        <Group justify="space-between">
          <Text>Frontend</Text>
          <Text c="dimmed">
            {__APP_VERSION__} ({shortSha(__GIT_SHA__)})
          </Text>
        </Group>
      </Stack>
    </Card>
  );
}

function DatabaseCard({ database }: { database: SystemStatus["database"] }) {
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={500}>Database</Text>
        {database.migrations_pending && (
          <Alert color="red" variant="light">
            Database revision ({database.current_revision ?? "none"}) does not match the running
            code's migrations ({database.head_revision ?? "none"}).
          </Alert>
        )}
        <Group justify="space-between">
          <Text>PostgreSQL</Text>
          <Text c="dimmed">{database.server_version}</Text>
        </Group>
        <Group justify="space-between">
          <Text>Size</Text>
          <Text c="dimmed">{formatBytes(database.size_bytes)}</Text>
        </Group>
        <Group justify="space-between">
          <Text>Connections</Text>
          <Text c="dimmed">{database.connection_count}</Text>
        </Group>
        <Group justify="space-between">
          <Text>Revision</Text>
          <Text c="dimmed">{database.current_revision ?? "none"}</Text>
        </Group>
      </Stack>
    </Card>
  );
}

function TablesCard({ tables }: { tables: SystemStatus["tables"] }) {
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={500}>Tables</Text>
        <Table>
          <Table.Tbody>
            {tables.map((table) => (
              <Table.Tr key={table.name}>
                <Table.Td>{table.name}</Table.Td>
                <Table.Td>{table.estimated_rows.toLocaleString()}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Stack>
    </Card>
  );
}

function UptimeCard({ status }: { status: SystemStatus }) {
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={500}>Uptime</Text>
        <Text c="dimmed">{formatUptime(status.uptime_seconds)}</Text>
        <Text size="xs" c="dimmed">
          Since {new Date(status.started_at).toLocaleString()}
        </Text>
      </Stack>
    </Card>
  );
}

function ConfigurationCard() {
  const config = useSystemConfig();

  if (config.isPending) {
    return (
      <Card withBorder>
        <Loader />
      </Card>
    );
  }
  if (config.isError) {
    return (
      <Card withBorder>
        <Alert color="red">Could not load configuration.</Alert>
      </Card>
    );
  }

  const holiday = config.data.holiday_subdivision
    ? `${config.data.holiday_country} / ${config.data.holiday_subdivision}`
    : config.data.holiday_country;
  const entries: [string, string][] = [
    ["App name", config.data.app_name],
    ["Debug mode", config.data.debug ? "on" : "off"],
    ["CORS origins", config.data.cors_origins.join(", ") || "none"],
    ["Access token lifetime", `${config.data.access_token_expire_minutes} min`],
    ["Auth cookie secure", config.data.auth_cookie_secure ? "yes" : "no"],
    ["Holiday calendar", holiday],
    ["Daily working hours", config.data.daily_working_hours],
  ];

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={500}>Configuration</Text>
        {entries.map(([label, value]) => (
          <Group key={label} justify="space-between">
            <Text>{label}</Text>
            <Text c="dimmed">{value}</Text>
          </Group>
        ))}
      </Stack>
    </Card>
  );
}

export function AdminSystemStatusPage() {
  const liveness = useProbe("live", () => api.GET("/api/v1/health"));
  const readiness = useProbe("ready", () => api.GET("/api/v1/health/ready"));
  const status = useSystemStatus();

  return (
    <Stack>
      <Title order={2}>System status</Title>
      <Card withBorder maw={480}>
        <Stack gap="sm">
          <ProbeRow name="API" probe={liveness} />
          <ProbeRow name="Database" probe={readiness} />
        </Stack>
      </Card>

      {status.isPending && <Loader />}
      {status.isError && <Alert color="red">Could not load system status.</Alert>}
      {status.data && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          <VersionsCard status={status.data} />
          <DatabaseCard database={status.data.database} />
          <TablesCard tables={status.data.tables} />
          <UptimeCard status={status.data} />
          <ConfigurationCard />
        </SimpleGrid>
      )}
    </Stack>
  );
}
