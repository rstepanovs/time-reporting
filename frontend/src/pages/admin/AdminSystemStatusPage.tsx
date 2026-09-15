import { Badge, Card, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "@/api/client";

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

export function AdminSystemStatusPage() {
  const liveness = useProbe("live", () => api.GET("/api/v1/health"));
  const readiness = useProbe("ready", () => api.GET("/api/v1/health/ready"));

  return (
    <Stack maw={480}>
      <Title order={2}>System status</Title>
      <Card withBorder>
        <Stack gap="sm">
          <ProbeRow name="API" probe={liveness} />
          <ProbeRow name="Database" probe={readiness} />
        </Stack>
      </Card>
    </Stack>
  );
}
