import { Button, Stack } from "@mantine/core";
import { Link } from "react-router";

import { DashboardCard } from "@/components/DashboardCard";
import { addWeeks, startOfIsoWeek, todayIso } from "@/timesheets/week";

/** Shortcuts to the two things a worker opens the dashboard to do: book today's time, or catch up
 * on last week. */
export function QuickActionsCard() {
  const previousWeekStart = addWeeks(startOfIsoWeek(todayIso()), -1);

  return (
    <DashboardCard title="Actions">
      <Stack gap="xs">
        <Button component={Link} to="/timesheet">
          Report time
        </Button>
        <Button component={Link} to={`/timesheet?week=${previousWeekStart}`} variant="default">
          Previous week
        </Button>
      </Stack>
    </DashboardCard>
  );
}
