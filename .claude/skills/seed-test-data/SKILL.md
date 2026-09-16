---
name: seed-test-data
description: >-
  Seed demo/test data into the local database for this repo (users,
  customers, projects, calendar holidays, timesheet entries) via the
  time-reporting CLI. Use whenever the user asks to seed the database, set up
  demo data, create a first admin account, or import public holidays for
  local development or testing. Idempotent — safe to re-run.
---

# Seed test/demo data

## Prerequisites

- Dependencies installed (`uv sync` at the repo root).
- Database migrated to head:
  `uv run alembic -c backend/alembic.ini upgrade head`
- Commands run from the repository root (the uv workspace root).

## Commands

```sh
# first admin account — needed before anything else if the DB is empty
uv run time-reporting create-admin --email you@example.com --name "You"

# demo users, customers, projects, calendar and timesheet entries
uv run time-reporting seed-demo

# add a year's public holidays to the shared calendar
uv run time-reporting import-holidays --year 2026
```

Each subcommand runs through a `Bus` built the same way a real HTTP request
would (see `cli.py`), so it exercises the same module handlers as the app.

## What `seed-demo` creates

- One user per access level plus a plain employee, all sharing the password
  **`demo-password`**:

  | user | email | levels |
  | --- | --- | --- |
  | Alice Admin | `admin@example.com` | `admin` |
  | Mark Manager | `manager@example.com` | `manager` |
  | Emma Employee | `employee@example.com` | *(none — a plain employee)* |
  | Andy Accountant | `accountant@example.com` | `accountant` |
  | Max Multi | `lead@example.com` | `admin`, `manager` |

  `worker@example.com` (the old single-role demo user) is no longer seeded,
  but is left untouched if it already exists in a dev database — seeding is
  idempotent by email.
- Active and archived customers, plus a few projects with members per
  customer — a `manager`-level demo user is set as `manager_id` on every
  active one. Projects are created for each customer *before* that customer
  is archived, since creating a project requires an active customer.
- The current and next year's public holidays, plus one demo bridge day.
- Normal working hours booked for every demo user who is a project member
  (`admin@example.com` isn't a member of any demo project, so has none) on
  every working day of the last 3 months, plus a little overtime/travel time
  each month — so the personal dashboard's month calendar and year-hours
  table both have data to show.
- Once a user's weeks are freshly booked, every week but the most recent is
  submitted then approved (reviewer: another `manager`-level demo user —
  nobody, not even an admin, reviews their own week), and the most recent is
  left submitted — so a fresh checkout's `/approvals` page has something
  waiting. This also leaves the current month's last week unapproved while
  earlier months are fully approved, so the manager dashboard's billing card
  naturally shows both a not-ready (current month) and a ready (an earlier
  month) project, with no extra seeding needed.

## Idempotency

`seed-demo` is safe to re-run: existing emails / customer or project names
are skipped, and the timesheet-entry booking step is guarded by an "already
has entries" check, so re-running doesn't duplicate data or re-submit/
re-approve weeks. `import-holidays --year` skips dates already present
(manually added or previously imported), so it's also safe to re-run for the
same year.

## Caveat for tests

The test database doubles as the dev database, so tests seed their own
uniquely-renamed copies of demo data rather than reusing `seed-demo`'s
records directly — keep that in mind if asked to add seed data for a test
rather than for local dev.

## Docker Compose

`docker compose up --build` already runs migrations via the one-shot
`migrate` service before `backend` starts; the seed/create-admin/
import-holidays commands above still need to be run manually (e.g.
`docker compose exec backend uv run time-reporting seed-demo`) — they are not
part of the compose startup.
