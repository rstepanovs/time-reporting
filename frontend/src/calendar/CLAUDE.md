# frontend calendar/

Backend: `modules/work_calendar`.

- `api.ts` — calendar days, non-working-day CRUD, public-holiday import, plus
  `NonWorkingDayConflictError` (409 date taken) / `NonWorkingDayNotFoundError` (404) /
  `CalendarRuleError` (400).
- `hooks.ts` — `calendarKeys` + `useCalendarDays`/`useNonWorkingDays` queries and
  add/update/delete/import mutations, all invalidating `calendarKeys.all`.
- `NonWorkingDayFormModal.tsx` — create/edit; `kind` is locked once editing, like a billing item's
  unit. Backs `pages/admin/AdminCalendarPage.tsx`.
