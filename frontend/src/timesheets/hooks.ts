import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getMonthCalendar,
  getMonthTimeSummary,
  getTimesheetWeek,
  getWeeklyHours,
  getYearHours,
  listTimesheetOptions,
  saveTimesheetWeek,
  type TimeEntryChange,
} from "@/timesheets/api";

export const timesheetKeys = {
  all: ["timesheets"] as const,
  week: (userId: string, weekStart: string) =>
    [...timesheetKeys.all, "week", userId, weekStart] as const,
  options: () => [...timesheetKeys.all, "options"] as const,
  summaries: () => [...timesheetKeys.all, "summaries"] as const,
  monthCalendar: (userId: string, year: number, month: number) =>
    [...timesheetKeys.summaries(), "calendar", userId, year, month] as const,
  yearHours: (userId: string, year: number) =>
    [...timesheetKeys.summaries(), "year", userId, year] as const,
  monthSummary: (userId: string, year: number, month: number) =>
    [...timesheetKeys.summaries(), "monthSummary", userId, year, month] as const,
  weeklyHours: (userId: string, weeks: number) =>
    [...timesheetKeys.summaries(), "weeklyHours", userId, weeks] as const,
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
      // The saved week may fall in the current month/year, so the dashboard's calendar and
      // year-hours table need fresh data too.
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.summaries() });
    },
  });
}

/** The dashboard's current-month calendar; `userId` selects whose month to load. */
export function useMonthCalendar(userId: string, year: number, month: number) {
  return useQuery({
    queryKey: timesheetKeys.monthCalendar(userId, year, month),
    queryFn: () => getMonthCalendar({ year, month, userId }),
  });
}

/** The dashboard's year-hours table; `userId` selects whose year to load. */
export function useYearHours(userId: string, year: number) {
  return useQuery({
    queryKey: timesheetKeys.yearHours(userId, year),
    queryFn: () => getYearHours({ year, userId }),
  });
}

/** One month's "My time" card (hours + benefits); `userId` selects whose month to load. */
export function useMonthTimeSummary(userId: string, year: number, month: number) {
  return useQuery({
    queryKey: timesheetKeys.monthSummary(userId, year, month),
    queryFn: () => getMonthTimeSummary({ year, month, userId }),
  });
}

/** The dashboard's hours-per-week chart and per-project table; `userId` selects whose weeks to
 * load. */
export function useWeeklyHours(userId: string, weeks: number) {
  return useQuery({
    queryKey: timesheetKeys.weeklyHours(userId, weeks),
    queryFn: () => getWeeklyHours({ weeks, userId }),
  });
}
