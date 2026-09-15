import { Button, Group, Stack, Title } from "@mantine/core";
import { Link } from "react-router";

import { useAuthenticatedUser } from "@/auth/hooks";
import { MonthCalendar } from "@/timesheets/MonthCalendar";
import { todayIso } from "@/timesheets/week";
import { YearHoursTable } from "@/timesheets/YearHoursTable";

export function DashboardPage() {
  const user = useAuthenticatedUser();
  const today = todayIso();
  const year = Number(today.slice(0, 4));
  const month = Number(today.slice(5, 7));

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>Dashboard</Title>
        <Button component={Link} to="/timesheet">
          Open this week's timesheet
        </Button>
      </Group>
      <MonthCalendar userId={user.id} year={year} month={month} today={today} />
      <YearHoursTable userId={user.id} year={year} />
    </Stack>
  );
}
