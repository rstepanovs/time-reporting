# work_calendar module

Owns `NonWorkingDay`: one company-wide calendar of public holidays, bridge days and company days off
(`NonWorkingDayKind`), each on a unique date. Weekends are computed, not stored.

- `GetCalendarDays(date_from, date_to)` (capped at 366 days) returns every day in the range flagged
  with `is_weekend` and its `NonWorkingDayDTO` if any — the one query the timesheets module and its UI
  need to render a week (and to compute expected hours).
- `ImportPublicHolidays(year)` adds a year's holidays from the `holidays` PyPI library for the country
  (and optional subdivision) in `Settings.holiday_country`/`holiday_subdivision`, skipping dates
  already present (manually added or previously imported) so it's safe to re-run; an unsupported
  country/subdivision raises `HolidayCountryNotSupportedError`. Also reachable via the
  `time-reporting import-holidays --year` CLI command.
- Any authenticated user reads the calendar; only admins add, edit (`day`/`name`; `kind` is
  immutable), delete or import.
