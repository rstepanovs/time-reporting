import { Group, SimpleGrid, Stack, Title } from "@mantine/core";
import { useState } from "react";

import { AdminShortcutsCard } from "@/admin/AdminShortcutsCard";
import { useAuthenticatedUser } from "@/auth/hooks";
import { canManage, isAccountant, isAdmin } from "@/auth/roles";
import { AccountantPlaceholderCard } from "@/timesheets/AccountantPlaceholderCard";
import type { TeamScope } from "@/timesheets/api";
import { MonthTimeCard } from "@/timesheets/MonthTimeCard";
import { MyProjectsCard } from "@/timesheets/MyProjectsCard";
import { ProjectBillingCard } from "@/timesheets/ProjectBillingCard";
import { QuickActionsCard } from "@/timesheets/QuickActionsCard";
import { TeamScopeToggle } from "@/timesheets/TeamScopeToggle";
import { TeamStaffCard } from "@/timesheets/TeamStaffCard";
import { TeamTimesheetsCard } from "@/timesheets/TeamTimesheetsCard";
import { previousMonth, todayIso } from "@/timesheets/week";
import { WeeklyHoursChart } from "@/timesheets/WeeklyHoursChart";
import { WeeklyProjectHoursCard } from "@/timesheets/WeeklyProjectHoursCard";

export function DashboardPage() {
  const user = useAuthenticatedUser();
  const today = todayIso();
  const year = Number(today.slice(0, 4));
  const month = Number(today.slice(5, 7));
  const previous = previousMonth(year, month);
  const [teamScope, setTeamScope] = useState<TeamScope>("mine");

  return (
    <Stack>
      <Title order={2}>Dashboard</Title>

      <Title order={3}>My time</Title>
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

      {canManage(user) && (
        <>
          <Group justify="space-between">
            <Title order={3}>My team</Title>
            <TeamScopeToggle scope={teamScope} onScopeChange={setTeamScope} />
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            <TeamTimesheetsCard scope={teamScope} />
            <ProjectBillingCard scope={teamScope} />
            <TeamStaffCard scope={teamScope} />
          </SimpleGrid>
        </>
      )}

      {isAccountant(user) && (
        <>
          <Title order={3}>Billing</Title>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            <AccountantPlaceholderCard />
          </SimpleGrid>
        </>
      )}

      {isAdmin(user) && (
        <>
          <Title order={3}>Administration</Title>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            <AdminShortcutsCard />
          </SimpleGrid>
        </>
      )}
    </Stack>
  );
}
