import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getTimesheetWeek,
  listTimesheetOptions,
  saveTimesheetWeek,
  type TimeEntryChange,
} from "@/timesheets/api";

export const timesheetKeys = {
  all: ["timesheets"] as const,
  week: (userId: string, weekStart: string) =>
    [...timesheetKeys.all, "week", userId, weekStart] as const,
  options: () => [...timesheetKeys.all, "options"] as const,
};

/** `userId` selects whose week to load; pass the viewer's own id for "my timesheet". */
export function useTimesheetWeek(userId: string, weekStart: string) {
  return useQuery({
    queryKey: timesheetKeys.week(userId, weekStart),
    queryFn: () => getTimesheetWeek({ weekStart, userId }),
  });
}

export function useTimesheetOptions() {
  return useQuery({
    queryKey: timesheetKeys.options(),
    queryFn: listTimesheetOptions,
  });
}

export function useSaveTimesheetWeek(userId: string, weekStart: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: TimeEntryChange[]) => saveTimesheetWeek(weekStart, changes),
    onSuccess: (week) => {
      queryClient.setQueryData(timesheetKeys.week(userId, weekStart), week);
    },
  });
}
