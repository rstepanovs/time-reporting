import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type TimesheetWeek = components["schemas"]["TimesheetWeekResponse"];
export type TimesheetWeekStatus = components["schemas"]["TimesheetWeekStatus"];
export type TimesheetWeekSummary = components["schemas"]["TimesheetWeekSummaryResponse"];
export type TimesheetRow = components["schemas"]["TimesheetRowResponse"];
export type TimesheetOption = components["schemas"]["TimesheetOptionResponse"];
export type TimeEntry = components["schemas"]["TimeEntryResponse"];
export type TimeEntryChange = components["schemas"]["TimeEntryChangeRequest"];
export type RowCommentChange = components["schemas"]["RowCommentChangeRequest"];

export type MonthCalendar = components["schemas"]["MonthCalendarResponse"];
export type CalendarWeekHours = components["schemas"]["CalendarWeekHoursResponse"];
export type CalendarDayHours = components["schemas"]["CalendarDayHoursResponse"];
export type YearHours = components["schemas"]["YearHoursResponse"];
export type MonthHours = components["schemas"]["MonthHoursResponse"];
export type ProjectHours = components["schemas"]["ProjectHoursResponse"];
export type HoursTotals = components["schemas"]["HoursTotalsResponse"];

export type MonthTimeSummary = components["schemas"]["MonthTimeSummaryResponse"];
export type CurrencyAmount = components["schemas"]["CurrencyAmountResponse"];
export type WeeklyHours = components["schemas"]["WeeklyHoursResponse"];
export type WeekHours = components["schemas"]["WeekHoursResponse"];

export type TeamMonthOverview = components["schemas"]["TeamMonthOverviewResponse"];
export type TeamProject = components["schemas"]["TeamProjectResponse"];
export type TeamMember = components["schemas"]["TeamMemberResponse"];
export type TeamMemberWeek = components["schemas"]["TeamMemberWeekResponse"];
export type TeamMemberWarning = components["schemas"]["TeamMemberResponse"]["warning"];
export type TeamStatusCounts = components["schemas"]["TeamStatusCountsResponse"];
export type ProjectBillingPeriod = components["schemas"]["ProjectBillingPeriodResponse"];
export type BillingPeriodStatus = components["schemas"]["ProjectBillingPeriodResponse"]["status"];
export type BillingPeriodListItem = components["schemas"]["BillingPeriodListItemResponse"];
export type BillingPeriodPage = components["schemas"]["BillingPeriodPageResponse"];
export type TeamScope = "mine" | "all";

/** A project/billing-item pair picked from the options list, before it has any entries — the
 * shape a draft row (added but not yet saved) takes in the grid. */
export type PickedRow = {
  project: TimesheetOption["project"];
  billing_item: TimesheetOption["billing_items"][number];
};

/** A rule was violated while reading/saving/reviewing a week (400/403/404). The backend's
 * message, or a generic one for a 403 that carries no body. */
export class TimesheetRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimesheetRuleError";
  }
}

/** The week's status doesn't allow this action (409) — e.g. saving a submitted week, or
 * submitting/approving/returning from the wrong status. The backend's message. */
export class TimesheetConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimesheetConflictError";
  }
}

async function timesheetAwareError(response: Response): Promise<Error> {
  if (response.status === 409) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new TimesheetConflictError(body?.detail ?? "This week's status has changed");
  }
  if (response.status === 400 || response.status === 404) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new TimesheetRuleError(body?.detail ?? "This action is not allowed");
  }
  if (response.status === 403) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new TimesheetRuleError(body?.detail ?? "You cannot view another user's timesheet");
  }
  return new ApiError(response);
}

export async function getTimesheetWeek(params: {
  weekStart: string;
  userId?: string;
}): Promise<TimesheetWeek> {
  const { data, response } = await api.GET("/api/v1/timesheets/weeks/{week_start}", {
    params: { path: { week_start: params.weekStart }, query: { user_id: params.userId } },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

export async function saveTimesheetWeek(
  weekStart: string,
  changes: TimeEntryChange[],
  rowComments: RowCommentChange[] = [],
): Promise<TimesheetWeek> {
  const { data, response } = await api.PUT("/api/v1/timesheets/weeks/{week_start}/entries", {
    params: { path: { week_start: weekStart } },
    body: { changes, row_comments: rowComments },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** Submit the caller's own week for review. */
export async function submitTimesheetWeek(weekStart: string): Promise<TimesheetWeek> {
  const { data, response } = await api.POST("/api/v1/timesheets/weeks/{week_start}/submit", {
    params: { path: { week_start: weekStart } },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** Approve `userId`'s submitted week (manager only). */
export async function approveTimesheetWeek(params: {
  weekStart: string;
  userId: string;
}): Promise<TimesheetWeek> {
  const { data, response } = await api.POST("/api/v1/timesheets/weeks/{week_start}/approve", {
    params: { path: { week_start: params.weekStart }, query: { user_id: params.userId } },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** Return `userId`'s submitted/approved week for corrections, with an explanatory comment. */
export async function returnTimesheetWeek(params: {
  weekStart: string;
  userId: string;
  comment: string;
}): Promise<TimesheetWeek> {
  const { data, response } = await api.POST("/api/v1/timesheets/weeks/{week_start}/return", {
    params: { path: { week_start: params.weekStart }, query: { user_id: params.userId } },
    body: { comment: params.comment },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** Weeks awaiting review, oldest submission first — a manager's approvals list. `scope: "mine"`
 * narrows to projects the caller manages; `"all"` (the default) matches the previous behavior. */
export async function listSubmittedTimesheetWeeks(
  params: { scope?: TeamScope } = {},
): Promise<TimesheetWeekSummary[]> {
  const { data, response } = await api.GET("/api/v1/timesheets/submissions", {
    params: { query: { scope: params.scope } },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** The caller's own project/billing-item picker, for adding a row. */
export async function listTimesheetOptions(): Promise<TimesheetOption[]> {
  const { data, response } = await api.GET("/api/v1/timesheets/options");
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** The dashboard's current-month calendar; `year`/`month` default to today's on the server. */
export async function getMonthCalendar(params: {
  year?: number;
  month?: number;
  userId?: string;
}): Promise<MonthCalendar> {
  const { data, response } = await api.GET("/api/v1/timesheets/calendar", {
    params: { query: { year: params.year, month: params.month, user_id: params.userId } },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** The dashboard's year-hours table: `year`'s hours by month, newest first. */
export async function getYearHours(params: { year: number; userId?: string }): Promise<YearHours> {
  const { data, response } = await api.GET("/api/v1/timesheets/years/{year}", {
    params: { path: { year: params.year }, query: { user_id: params.userId } },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** One month's booked time (hours + benefits), for a dashboard "My time" card. */
export async function getMonthTimeSummary(params: {
  year: number;
  month: number;
  userId?: string;
}): Promise<MonthTimeSummary> {
  const { data, response } = await api.GET("/api/v1/timesheets/months/{year}/{month}/summary", {
    params: {
      path: { year: params.year, month: params.month },
      query: { user_id: params.userId },
    },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** `weeks` ISO weeks ending with today's week, oldest first, for the dashboard's hours-per-week
 * chart and per-project table. */
export async function getWeeklyHours(params: {
  weeks: number;
  userId?: string;
}): Promise<WeeklyHours> {
  const { data, response } = await api.GET("/api/v1/timesheets/weekly-hours", {
    params: { query: { weeks: params.weeks, user_id: params.userId } },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** A manager's team for one calendar month: every project they manage (`scope: "mine"`, the
 * default) or, for an admin, every active project (`"all"`). */
export async function getTeamMonthOverview(params: {
  year: number;
  month: number;
  scope?: TeamScope;
}): Promise<TeamMonthOverview> {
  const { data, response } = await api.GET("/api/v1/timesheets/team/{year}/{month}", {
    params: {
      path: { year: params.year, month: params.month },
      query: { scope: params.scope },
    },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** Send a project's calendar month to billing: a stub that records the handoff and locks the
 * period. Throws `TimesheetRuleError` (not this project's manager) or `TimesheetConflictError`
 * (not ready yet, or already sent). */
export async function sendProjectMonthToBilling(params: {
  projectId: string;
  year: number;
  month: number;
}): Promise<ProjectBillingPeriod> {
  const { data, response } = await api.POST("/api/v1/timesheets/billing-periods", {
    body: { project_id: params.projectId, year: params.year, month: params.month },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** Admin only: every sent billing period, newest first, filterable by project/customer/month
 * range and paginated. */
export async function listBillingPeriods(params: {
  projectId?: string;
  customerId?: string;
  monthFrom?: string;
  monthTo?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<BillingPeriodPage> {
  const { data, response } = await api.GET("/api/v1/timesheets/billing-periods", {
    params: {
      query: {
        project_id: params.projectId,
        customer_id: params.customerId,
        month_from: params.monthFrom,
        month_to: params.monthTo,
        limit: params.limit,
        offset: params.offset,
      },
    },
  });
  if (!data) throw await timesheetAwareError(response);
  return data;
}

/** Admin only: delete a sent billing period, unlocking it again. */
export async function reopenProjectBillingPeriod(params: {
  projectId: string;
  periodStart: string;
}): Promise<void> {
  const { response } = await api.DELETE(
    "/api/v1/timesheets/billing-periods/{project_id}/{period_start}",
    { params: { path: { project_id: params.projectId, period_start: params.periodStart } } },
  );
  if (!response.ok) throw await timesheetAwareError(response);
}
