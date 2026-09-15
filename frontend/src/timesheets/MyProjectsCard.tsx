import { Alert, Anchor, List, Loader, Text } from "@mantine/core";
import { Link } from "react-router";

import { DashboardCard } from "@/components/DashboardCard";
import { useTimesheetOptions } from "@/timesheets/hooks";

/** The projects the signed-in user can currently book time against. */
export function MyProjectsCard() {
  const query = useTimesheetOptions();

  if (query.isPending) {
    return (
      <DashboardCard title="My projects">
        <Loader size="sm" />
      </DashboardCard>
    );
  }
  if (query.isError || !query.data) {
    return (
      <DashboardCard title="My projects">
        <Alert color="red">Could not load your projects.</Alert>
      </DashboardCard>
    );
  }

  const options = query.data;

  if (options.length === 0) {
    return (
      <DashboardCard title="My projects">
        <Text size="sm" c="dimmed">
          You are not a member of any project yet.
        </Text>
      </DashboardCard>
    );
  }

  return (
    <DashboardCard title="My projects">
      <List spacing={4} size="sm" listStyleType="none">
        {options.map((option) => (
          <List.Item key={option.project.id}>
            <Anchor component={Link} to={`/projects/${option.project.id}`} size="sm">
              {option.project.customer.name} · {option.project.name}
            </Anchor>
          </List.Item>
        ))}
      </List>
    </DashboardCard>
  );
}
