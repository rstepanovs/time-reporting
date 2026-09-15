/** Week/date helpers for the timesheet grid. Dates are plain ISO strings ("YYYY-MM-DD") end to
 * end — parsed to a local-midnight `Date` only to do arithmetic, then formatted straight back, so
 * there's no timezone drift from treating a calendar date as an instant. */

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function todayIso(): string {
  return toIsoDate(new Date());
}

export function addDays(iso: string, days: number): string {
  const date = parseIsoDate(iso);
  date.setDate(date.getDate() + days);
  return toIsoDate(date);
}

export function addWeeks(weekStart: string, weeks: number): string {
  return addDays(weekStart, weeks * 7);
}

/** The Monday (ISO date) of the week containing `iso`. */
export function startOfIsoWeek(iso: string): string {
  const date = parseIsoDate(iso);
  const isoWeekday = (date.getDay() + 6) % 7; // Mon=0..Sun=6
  date.setDate(date.getDate() - isoWeekday);
  return toIsoDate(date);
}

/** The 7 ISO dates of the week starting at `weekStart` (assumed to be a Monday). */
export function weekDays(weekStart: string): string[] {
  return Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
}

export function isWeekend(iso: string): boolean {
  const isoWeekday = parseIsoDate(iso).getDay();
  return isoWeekday === 0 || isoWeekday === 6;
}

/** Short day-of-week + day.month, e.g. "Mon 14.09". */
export function formatDayLabel(iso: string): string {
  const date = parseIsoDate(iso);
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${WEEKDAY_LABELS[(date.getDay() + 6) % 7]} ${day}.${month}`;
}

/** "14 Sep – 20 Sep 2026" (or "14 – 20 Sep 2026" when both ends share a month). */
export function formatWeekLabel(weekStart: string): string {
  const start = parseIsoDate(weekStart);
  const end = parseIsoDate(addDays(weekStart, 6));
  const startMonth = start.toLocaleDateString(undefined, { month: "short" });
  const endMonth = end.toLocaleDateString(undefined, { month: "short" });
  const year = end.getFullYear();
  const startLabel = startMonth === endMonth ? `${start.getDate()}` : `${start.getDate()} ${startMonth}`;
  return `${startLabel} – ${end.getDate()} ${endMonth} ${year}`;
}

/** "September 2026". */
export function formatMonthLabel(year: number, month: number): string {
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

/** A decimal-string quantity from the API, formatted to 2 places, e.g. "8.00" -> "8". Trailing
 * zeros (and a trailing decimal point) are dropped so whole hours don't carry ".00" everywhere. */
export function formatHours(value: string): string {
  return Number(value).toFixed(2).replace(/\.?0+$/, "");
}

/** `year`/`month` shifted by `delta` whole months (`month` is 1-12), carrying over into the year. */
export function addMonths(
  year: number,
  month: number,
  delta: number,
): { year: number; month: number } {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (((index % 12) + 12) % 12) + 1 };
}

/** The year/month one month before `year`/`month`. */
export function previousMonth(year: number, month: number): { year: number; month: number } {
  return addMonths(year, month, -1);
}

/** "W38" (the ISO year isn't shown — it only ever differs from the calendar year for the one or
 * two weeks spanning New Year's, where the surrounding chart labels make it unambiguous). */
export function formatIsoWeekLabel(isoWeek: number): string {
  return `W${isoWeek}`;
}

/** Reported hours as a percentage of expected hours, rounded to the nearest whole percent, or
 * `null` when nothing was expected (so "percent full" is meaningless rather than 0 or Infinity). */
export function fillRatePercent(hours: string, expectedHours: string): number | null {
  const expected = Number(expectedHours);
  if (expected <= 0) return null;
  return Math.round((Number(hours) / expected) * 100);
}
