import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type CalendarDay = components["schemas"]["CalendarDayResponse"];
export type NonWorkingDay = components["schemas"]["NonWorkingDayResponse"];
export type NonWorkingDayKind = components["schemas"]["NonWorkingDayKind"];

/** A non-working day already exists on that date (409). */
export class NonWorkingDayConflictError extends Error {
  constructor() {
    super("A non-working day already exists on this date");
    this.name = "NonWorkingDayConflictError";
  }
}

export class NonWorkingDayNotFoundError extends Error {
  constructor() {
    super("Non-working day not found");
    this.name = "NonWorkingDayNotFoundError";
  }
}

/** A business rule was violated, e.g. an unsupported holiday country (400). The backend's message. */
export class CalendarRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CalendarRuleError";
  }
}

async function calendarAwareError(response: Response): Promise<Error> {
  if (response.status === 409) return new NonWorkingDayConflictError();
  if (response.status === 404) return new NonWorkingDayNotFoundError();
  if (response.status === 400) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new CalendarRuleError(body?.detail ?? "This action is not allowed");
  }
  return new ApiError(response);
}

/** Every day from `from` to `to` (inclusive, ISO dates), flagged as a weekend/non-working day. */
export async function getCalendarDays(range: { from: string; to: string }): Promise<CalendarDay[]> {
  const { data, response } = await api.GET("/api/v1/calendar/days", { params: { query: range } });
  if (!data) throw await calendarAwareError(response);
  return data;
}

export async function listNonWorkingDays(year?: number): Promise<NonWorkingDay[]> {
  const { data, response } = await api.GET("/api/v1/calendar/non-working-days", {
    params: { query: { year } },
  });
  if (!data) throw await calendarAwareError(response);
  return data;
}

export async function addNonWorkingDay(body: {
  day: string;
  name: string;
  kind: NonWorkingDayKind;
}): Promise<NonWorkingDay> {
  const { data, response } = await api.POST("/api/v1/calendar/non-working-days", { body });
  if (!data) throw await calendarAwareError(response);
  return data;
}

export async function updateNonWorkingDay(
  id: string,
  body: { day?: string; name?: string },
): Promise<NonWorkingDay> {
  const { data, response } = await api.PATCH("/api/v1/calendar/non-working-days/{non_working_day_id}", {
    params: { path: { non_working_day_id: id } },
    body,
  });
  if (!data) throw await calendarAwareError(response);
  return data;
}

export async function deleteNonWorkingDay(id: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/calendar/non-working-days/{non_working_day_id}", {
    params: { path: { non_working_day_id: id } },
  });
  if (!response.ok) throw await calendarAwareError(response);
}

/** Adds the configured country's public holidays for `year`; returns how many were added. */
export async function importPublicHolidays(year: number): Promise<number> {
  const { data, response } = await api.POST("/api/v1/calendar/non-working-days/import", {
    body: { year },
  });
  if (!data) throw await calendarAwareError(response);
  return data.added;
}
