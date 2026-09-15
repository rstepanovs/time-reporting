# frontend test/

- `setup.ts` — Vitest setup (jsdom polyfills for `matchMedia`/`ResizeObserver`/`document.fonts` that
  Mantine needs, RTL cleanup, and cleaning `@mantine/notifications`'s module-level queue — it
  outlives the React tree, so a toast shown in one test would otherwise still be queued when the next
  test's `<Notifications />` mounts). Wired in via `vite.config.ts`'s `test.setupFiles`.
- `renderApp.tsx` — renders the full route tree in a memory router with a fresh `QueryClient`.
  Tests mock `@/auth/api` and whichever of `@/projects/api` / `@/customers/api` / `@/users/api` /
  `@/admin/api` / `@/calendar/api` / `@/timesheets/api` the page under test calls.
- `fixtures.ts` — one `CurrentUser` per access-level persona used across tests: `testManager`
  (`["manager"]`), `testEmployee` (`[]`, the implicit baseline — no levels), `testAdmin`
  (`["admin","manager"]`, so it passes both `AdminDep`- and `ManagerDep`-gated views at once) and
  `testAdminOnly` (`["admin"]`, for asserting the admin-without-manager case, e.g. Administration
  visible but Approvals/Team hidden).

## Mantine gotchas

- `DatePickerInput` renders its trigger as a button, not a text input — editing its pre-filled value
  in a test is awkward, so prefer a flow (e.g. edit rather than create) that doesn't need to change
  it.
- `Select` renders an input with `role="combobox"`, not `"textbox"`.
- A required field's `<label>` includes a trailing `*`, so match it with a prefix regex (e.g.
  `getByLabelText(/^name/i)`) rather than the exact label text.
