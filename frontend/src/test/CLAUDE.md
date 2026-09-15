# frontend test/

- `setup.ts` — Vitest setup (jsdom polyfills for `matchMedia`/`ResizeObserver`/`document.fonts` that
  Mantine needs, RTL cleanup, and cleaning `@mantine/notifications`'s module-level queue — it
  outlives the React tree, so a toast shown in one test would otherwise still be queued when the next
  test's `<Notifications />` mounts). Wired in via `vite.config.ts`'s `test.setupFiles`.
- `renderApp.tsx` — renders the full route tree in a memory router with a fresh `QueryClient`.
  Tests mock `@/auth/api` and whichever of `@/projects/api` / `@/customers/api` / `@/users/api` /
  `@/admin/api` / `@/calendar/api` / `@/timesheets/api` the page under test calls.

## Mantine gotchas

- `DatePickerInput` renders its trigger as a button, not a text input — editing its pre-filled value
  in a test is awkward, so prefer a flow (e.g. edit rather than create) that doesn't need to change
  it.
- `Select` renders an input with `role="combobox"`, not `"textbox"`.
- A required field's `<label>` includes a trailing `*`, so match it with a prefix regex (e.g.
  `getByLabelText(/^name/i)`) rather than the exact label text.
