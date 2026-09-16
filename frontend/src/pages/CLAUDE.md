# frontend pages/

Pages are thin compositions; their behavior is documented with the feature area they use. Read that
area's `CLAUDE.md` before changing a page:

| Page | Route | Documented in |
| --- | --- | --- |
| `LoginPage` | `/login` | `auth/CLAUDE.md` |
| `DashboardPage` | `/` | `timesheets/CLAUDE.md` (sections by access level: My time/My team/Billing), `admin/CLAUDE.md` (Administration section) |
| `TimesheetPage` | `/timesheet?week=&user=` | `timesheets/CLAUDE.md` (weekly grid) |
| `HoursPage` | `/hours?month=` | `timesheets/CLAUDE.md` (hours views) |
| `ApprovalsPage` | `/approvals?scope=` | `timesheets/CLAUDE.md` (manager views) |
| `TeamPage` | `/team?scope=&month=` | `timesheets/CLAUDE.md` (manager views) |
| `ProjectsPage`, `ProjectDetailsPage` | `/projects`, `/projects/:projectId` | `projects/CLAUDE.md` |
| `ChangePasswordPage` | `/account/password` | `auth/CLAUDE.md` |
| `admin/*` | `/admin/...` | `admin/CLAUDE.md` (`AdminBillingPage` also uses `timesheets/CLAUDE.md`) |
| `NotFoundPage` | `*` (and non-permitted `RequireRole` routes) | `auth/CLAUDE.md` (`RequireRole`) |
