/** How a dashboard calendar day compares to what was expected of it, for coloring the cell. */

import type { CalendarDayHours } from "@/timesheets/api";

export type DayStatus = "off" | "future" | "today" | "complete" | "partial" | "missing" | "extra";

/** `todayIso` is the viewer's "today" (`YYYY-MM-DD`), so this stays pure and testable. */
export function dayStatus(day: CalendarDayHours, todayIso: string): DayStatus {
  const hours = Number(day.hours);
  const expected = Number(day.expected_hours);
  const iso = day.calendar_day.day;

  if (hours > 0 && !day.is_working_day) return "extra";
  if (iso === todayIso) return "today";
  if (!day.is_working_day) return "off";
  if (iso > todayIso) return "future";
  if (expected > 0 && hours >= expected) return "complete";
  if (hours > 0) return "partial";
  return "missing";
}
