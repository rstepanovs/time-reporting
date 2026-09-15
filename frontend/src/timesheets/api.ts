import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type TimesheetWeek = components["schemas"]["TimesheetWeekResponse"];
export type TimesheetRow = components["schemas"]["TimesheetRowResponse"];
export type TimesheetOption = components["schemas"]["TimesheetOptionResponse"];
export type TimeEntry = components["schemas"]["TimeEntryResponse"];
export type TimeEntryChange = components["schemas"]["TimeEntryChangeRequest"];

export type MonthCalendar = components["schemas"]["MonthCalendarResponse"];
export type CalendarWeekHours = components["schemas"]["CalendarWeekHoursResponse"];
export type CalendarDayHours = components["schemas"]["CalendarDayHoursResponse"];
export type YearHours = components["schemas"]["YearHoursResponse"];
export type MonthHours = components["schemas"]["MonthHoursResponse"];
export type ProjectHours = components["schemas"]["ProjectHoursResponse"];
export type HoursTotals = components["schemas"]["HoursTotalsResponse"];

/** A project/billing-item pair picked from the options list, before it has any entries — the
 * shape a draft row (added but not yet saved) takes in the grid. */
export type PickedRow = {
  project: TimesheetOption["project"];
  billing_item: TimesheetOption["billing_items"][number];
};

/** A rule was violated while reading/saving a week (400/403/404). The backend's message, or a
 * generic one for the 403 "not your timesheet" case (which carries no body). */
export class TimesheetRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimesheetRuleError";
  }
}

async function timesheetAwareError(response: Response): Promise<Error> {
  if (response.status === 400 || response.status === 404) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new TimesheetRuleError(body?.detail ?? "This action is not allowed");
  }
  if (response.status === 403) {
    return new TimesheetRuleError("You cannot view another user's timesheet");
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
): Promise<TimesheetWeek> {
  const { data, response } = await api.PUT("/api/v1/timesheets/weeks/{week_start}/entries", {
    params: { path: { week_start: weekStart } },
    body: { changes },
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
