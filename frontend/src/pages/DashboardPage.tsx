import { SimpleGrid, Stack, Title } from "@mantine/core";

import { useAuthenticatedUser } from "@/auth/hooks";
import { MonthTimeCard } from "@/timesheets/MonthTimeCard";
import { MyProjectsCard } from "@/timesheets/MyProjectsCard";
import { QuickActionsCard } from "@/timesheets/QuickActionsCard";
import { previousMonth, todayIso } from "@/timesheets/week";
import { WeeklyHoursChart } from "@/timesheets/WeeklyHoursChart";
import { WeeklyProjectHoursCard } from "@/timesheets/WeeklyProjectHoursCard";

export function DashboardPage() {
  const user = useAuthenticatedUser();
  const today = todayIso();
  const year = Number(today.slice(0, 4));
  const month = Number(today.slice(5, 7));
  const previous = previousMonth(year, month);

  return (
    <Stack>
      <Title order={2}>Dashboard</Title>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3, xl: 5 }}>
        <QuickActionsCard />
        <MonthTimeCard userId={user.id} year={year} month={month} highlighted />
        <MonthTimeCard userId={user.id} year={previous.year} month={previous.month} />
        <WeeklyHoursChart userId={user.id} />
        <WeeklyProjectHoursCard userId={user.id} />
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3, xl: 5 }}>
        <MyProjectsCard />
      </SimpleGrid>
    </Stack>
  );
}
