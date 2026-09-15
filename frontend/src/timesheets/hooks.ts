import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approveTimesheetWeek,
  getMonthCalendar,
  getMonthTimeSummary,
  getTeamMonthOverview,
  getTimesheetWeek,
  getWeeklyHours,
  getYearHours,
  listSubmittedTimesheetWeeks,
  listTimesheetOptions,
  reopenProjectBillingPeriod,
  returnTimesheetWeek,
  saveTimesheetWeek,
  sendProjectMonthToBilling,
  submitTimesheetWeek,
  type RowCommentChange,
  type TeamScope,
  type TimeEntryChange,
} from "@/timesheets/api";

export const timesheetKeys = {
  all: ["timesheets"] as const,
  weeks: () => [...timesheetKeys.all, "week"] as const,
  week: (userId: string, weekStart: string) =>
    [...timesheetKeys.weeks(), userId, weekStart] as const,
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
  // A shared prefix, for invalidating every scope variant at once; the query itself keys off
  // `submissions(scope)` below, one cache entry per scope.
  allSubmissions: () => [...timesheetKeys.all, "submissions"] as const,
  submissions: (scope?: TeamScope) => [...timesheetKeys.allSubmissions(), scope] as const,
  team: () => [...timesheetKeys.all, "team"] as const,
  teamMonth: (year: number, month: number, scope?: TeamScope) =>
    [...timesheetKeys.team(), year, month, scope] as const,
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
    mutationFn: ({
      changes,
      rowComments = [],
    }: {
      changes: TimeEntryChange[];
      rowComments?: RowCommentChange[];
    }) => saveTimesheetWeek(weekStart, changes, rowComments),
    onSuccess: (week) => {
      queryClient.setQueryData(timesheetKeys.week(userId, weekStart), week);
      // The saved week may fall in the current month/year, so the dashboard's calendar and
      // year-hours table need fresh data too, along with the manager team overview.
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.summaries() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.team() });
    },
  });
}

/** Submit the caller's own week for review; `userId`/`weekStart` select the cached week to
 * update on success. */
export function useSubmitTimesheetWeek(userId: string, weekStart: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => submitTimesheetWeek(weekStart),
    onSuccess: (week) => {
      queryClient.setQueryData(timesheetKeys.week(userId, weekStart), week);
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.allSubmissions() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.team() });
    },
  });
}

/** Approve `userId`'s week; also refreshes the approvals list. */
export function useApproveTimesheetWeek(userId: string, weekStart: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => approveTimesheetWeek({ weekStart, userId }),
    onSuccess: (week) => {
      queryClient.setQueryData(timesheetKeys.week(userId, weekStart), week);
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.allSubmissions() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.team() });
    },
  });
}

/** Return `userId`'s week with a comment; also refreshes the approvals list. */
export function useReturnTimesheetWeek(userId: string, weekStart: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (comment: string) => returnTimesheetWeek({ weekStart, userId, comment }),
    onSuccess: (week) => {
      queryClient.setQueryData(timesheetKeys.week(userId, weekStart), week);
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.allSubmissions() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.team() });
    },
  });
}

/** The manager's approvals list: weeks awaiting review. `scope: "mine"` narrows to projects the
 * caller manages. */
export function useSubmittedTimesheetWeeks(scope?: TeamScope) {
  return useQuery({
    queryKey: timesheetKeys.submissions(scope),
    queryFn: () => listSubmittedTimesheetWeeks({ scope }),
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

/** A manager's team for one calendar month; `scope: "mine"` (the default) is their own projects,
 * `"all"` (admin only) is every active project. */
export function useTeamMonthOverview(year: number, month: number, scope?: TeamScope) {
  return useQuery({
    queryKey: timesheetKeys.teamMonth(year, month, scope),
    queryFn: () => getTeamMonthOverview({ year, month, scope }),
  });
}

/** Send a project's calendar month to billing; refreshes the team overview, the approvals list
 * and every cached week (locks may have changed which cells/actions they allow). */
export function useSendProjectMonthToBilling() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: sendProjectMonthToBilling,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.team() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.allSubmissions() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.weeks() });
    },
  });
}

/** Admin only: reopen a sent billing period. Same invalidation as sending one. */
export function useReopenProjectBillingPeriod() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: reopenProjectBillingPeriod,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.team() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.allSubmissions() });
      void queryClient.invalidateQueries({ queryKey: timesheetKeys.weeks() });
    },
  });
}
