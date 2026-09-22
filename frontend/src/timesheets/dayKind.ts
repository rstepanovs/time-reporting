/** What kind of day a calendar cell is: a plain workday, a weekend, or one of the shared
 * calendar's non-working-day kinds. Shared between the weekly grid (`TimesheetGrid`) and the
 * dashboard's month calendar (`MonthCalendar`) so both highlight days the same way. */

import type { CalendarDay, NonWorkingDayKind } from "@/calendar/api";

export type DayKind = "weekend" | "workday" | NonWorkingDayKind;

export function dayKind(day: Pick<CalendarDay, "is_weekend" | "non_working_day">): DayKind {
  return day.non_working_day?.kind ?? (day.is_weekend ? "weekend" : "workday");
}

/** A CSS color for the day's background, or `undefined` for a plain workday. */
export function dayKindBackground(kind: DayKind): string | undefined {
  switch (kind) {
    case "weekend":
    case "public_holiday":
      return "var(--mantine-color-red-light)";
    case "bridge_day":
    case "company_day_off":
      return "var(--mantine-color-yellow-light)";
    default:
      return undefined;
  }
}
