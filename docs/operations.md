# Operations runbook

Running a Time Reporting deployment with Docker Compose: install, upgrade, rollback, backups,
restore and the optional pgAdmin profile. Everything here assumes `compose.yaml` at the repository
root and a `.env` next to it (`cp .env.example .env`, then fill in `JWT_SECRET_KEY` and anything
else you want to change).

## Install

```sh
git clone <repository-url>
cd time-reporting
cp .env.example .env
# Generate a secret and paste it into .env's JWT_SECRET_KEY:
openssl rand -hex 32

docker compose up --build -d
```

`backend`'s image build needs outbound HTTPS to GitHub: `faktura-printer` (PDF invoice rendering,
`invoices/rendering.py`) is pinned to a tag straight from GitHub rather than an index (see
`backend/pyproject.toml`), so the builder stage installs `git` and `uv sync` fetches it from there;
the runtime stage also installs WeasyPrint's system libraries (Pango/HarfBuzz/fonts) alongside the
PostgreSQL client — the accountant package's `summary.pdf` (`accounting/rendering.py`) uses the
same libraries directly, not through `faktura-printer`. None of this needs network access again
after the image is built.

To pick up a new `faktura-printer` release (a new invoice/company-profile field, a template fix,
…): bump the tag in `backend/pyproject.toml`'s `faktura-printer @ git+https://github.com/
rstepanovs/faktura-printer@<tag>` dependency line, then `uv sync` at the repository root to update
`uv.lock` to the new commit and commit both files together. There is no compatibility range to
respect — pin exactly one tag, the same one every environment installs from the lock file.

`compose.yaml` brings the stack up in dependency order: `db` → `migrate` (creates the schema, since
there's nothing to back up yet) → `backend`/`backup` → `frontend`. Create the first administrator
once the backend is up:

```sh
docker compose exec backend time-reporting create-admin --email you@example.com --name "You"
```

Frontend: `http://<host>:8080`. API docs: `http://<host>:8000/api/docs`.

## Running a second deployment on the same machine

Useful for keeping a real deployment (real customers, real invoices) separate from an ongoing
development checkout, without ever transferring data between them — each deployment's database
just gets migrated in place as its own checkout is upgraded.

Give the second deployment its own working tree, since `scripts/upgrade.sh` runs `git checkout`/
`git pull` in whatever directory it's run from — sharing one checkout between two deployments would
mean upgrading one always disturbs the other. A `git worktree` is the cheapest way to do that: it's
a second working directory backed by the same repository (`.git`), so both stay in sync with a
single `git fetch`, with no second clone to keep up to date by hand.

Git refuses to have the same branch checked out in two worktrees at once, so if the development
checkout has `main` checked out, the second worktree has to be **detached** (checked out at a
specific commit/tag, not a branch) — which is the right shape for a deployment anyway: it upgrades
only when *you* choose to move it, by passing an explicit ref to `scripts/upgrade.sh`, never a bare
`git pull`.

```sh
git worktree add --detach ../time-reporting-prod main   # or a tag, once you tag releases
cd ../time-reporting-prod
cp .env.example .env
```

In that `.env`, set values that don't collide with the other deployment's:

```
COMPOSE_PROJECT_NAME=time-reporting-prod
BACKEND_PORT=18000
FRONTEND_PORT=18080
POSTGRES_PORT=15432
PGADMIN_PORT=15050
```

(`COMPOSE_PROJECT_NAME` is what keeps the two deployments' containers, networks and named volumes
from colliding — without it, both directories would default to the same project name and fight
over the same `db-data`/`backups`/`attachments` volumes.) Generate its own `JWT_SECRET_KEY` too —
never reuse one between deployments. Then follow Install above from `docker compose up --build -d`.

Each deployment is upgraded independently with `scripts/upgrade.sh [ref]`, run from its own
directory. Because the prod worktree is detached, always pass an explicit ref — a tag once releases
are tagged, otherwise `origin/main` (`scripts/upgrade.sh origin/main`; the *local* branch name
`main` doesn't work here — git refuses to check out a branch that's already checked out in another
worktree, even into detached HEAD, but a remote-tracking ref like `origin/main` isn't that branch
and checks out fine detached). The bare no-arg form (`git pull --ff-only`) only works on a directory
that has a branch checked out, so don't use it here either.

## Upgrade

```sh
scripts/upgrade.sh [ref]
```

`ref` is a branch, tag or commit to check out; omit it to fast-forward the current branch instead.
The script (`set -euo pipefail`, stops at the first failure):

1. Refuses to run with a dirty working tree.
2. Checks out `ref` (or `git pull --ff-only`).
3. `docker compose build`, with `GIT_SHA` set to the new commit's short hash — this is what the
   admin system status page (`/admin/status`) reports as the running backend/frontend version.
4. `docker compose run --rm migrate` — backs up the database first (skipped only if it isn't
   migrated yet or is already at head) and applies pending migrations. Run explicitly, and before
   anything else restarts, so a failure here is visible and stops the upgrade.
5. `docker compose up -d` to restart `backend`/`backup`/`frontend` on the new images.

If step 4 fails, nothing has been restarted yet — the previous images are still running. Fix the
issue (or roll back, below) before retrying.

## Rollback

There is no `alembic downgrade` in production (see below) — rolling back means running the
previous code against a database restored from the backup `migrate` made right before the upgrade
that's being undone.

```sh
# 1. Find the backup migrate made right before the upgrade — newest first, via the admin UI
#    (/admin/backups) or:
docker compose exec backend ls -t /var/backups/time-reporting

# 2. Check out the previous ref and rebuild, but don't restart yet:
git checkout <previous-ref>
export GIT_SHA=$(git rev-parse --short HEAD)
docker compose build

# 3. Stop the backend so nothing writes to the database during the restore:
docker compose stop backend

# 4. Restore (destructive: replaces the database's contents with the backup's):
docker compose run --rm migrate time-reporting restore <file> --yes

# 5. Start the stack on the rolled-back images:
docker compose up -d
```

## Backups

- `time-reporting backup` (`pg_dump --format=custom`) writes to `backup_dir`
  (`/var/backups/time-reporting` in Compose, the `backups` named volume, shared by `backend`,
  `migrate` and `backup`) as `time-reporting-<UTC timestamp>-<alembic revision>.dump`; only the
  newest `BACKUP_RETENTION_COUNT` (default 14) are kept.
- Alongside the dump, it also writes `time-reporting-<same timestamp>-<same
  revision>-attachments.tar.gz` — a tar of `attachment_dir` (the expense-report receipt/invoice
  scans, `/var/lib/time-reporting/attachments` in Compose, the `attachments` volume) — so one
  backup operation covers both, kept and pruned together. Skipped (no second file, and
  `attachments_size_bytes` is `null` in the API/CLI output) only if `attachment_dir` has never
  been created, i.e. no attachment has ever been uploaded.
- The `backup` service runs it on a loop, every `BACKUP_INTERVAL_HOURS` (default 24h); `migrate`
  also runs one (`--if-pending-migrations`, skipped if the database isn't migrated yet or is
  already at head) before every upgrade.
- List, create on demand and download backups from `/admin/backups` in the app, or create one from
  the CLI: `docker compose exec backend time-reporting backup`.
- Copy backups off-host regularly — a copy on the same disk as `db-data` doesn't survive a disk
  failure. From the host:

  ```sh
  docker run --rm -v time-reporting_backups:/backups -v "$PWD":/dest alpine \
    cp /backups/<file> /dest/
  ```

  Remember to also copy the matching `*-attachments.tar.gz`, if one exists.

## Restore

`time-reporting restore <file> --yes` (`pg_restore --clean --if-exists --single-transaction
--no-owner`) replaces the current database's contents with the backup's, and — if
`<file minus .dump>-attachments.tar.gz` sits next to it — replaces the whole contents of
`attachment_dir` with that archive's too. If the archive is missing, the restore still proceeds
(only a warning is logged); any `expense_attachments` row in the restored database then points at
a file that doesn't exist, which the app already tolerates (the download/list views just treat it
as gone, the same as a manually deleted upload). It is **CLI-only**, deliberately not exposed over
HTTP or from the admin UI — see [Rollback](#rollback) for the full sequence (stop `backend` first,
so nothing writes mid-restore). Without `--yes` it refuses to run. The command also prints the
alembic revision recorded in the backup's file name, so you can confirm it matches the code you're
about to run before continuing.

## Orphaned attachment files

Uploading an expense-report attachment writes its file, then its database row, in that order —
not one transaction. If a command fails or the process is killed between the two, the file is
never referenced by any row. `time-reporting prune-attachments` (add `--dry-run` to only list what
it would remove) deletes every file under `attachment_dir` that no `expense_attachments` row
references; safe to run at any time, including on a schedule alongside backups.

## pgAdmin

Optional, for ad hoc SQL access:

```sh
docker compose --profile tools up -d pgadmin
```

Bound to `127.0.0.1:${PGADMIN_PORT:-5050}` only — not reachable from outside the host. The `db`
server is pre-registered (`deploy/pgadmin/servers.json`); sign in with `PGADMIN_EMAIL`/
`PGADMIN_PASSWORD` from `.env`, then the server's own password (`POSTGRES_PASSWORD`).

On a remote host, reach it through an SSH tunnel rather than changing the bind address:

```sh
ssh -L 5050:localhost:5050 <user>@<host>
# then open http://localhost:5050 locally
```

## Why no in-app upgrade, and no production `alembic downgrade`

- **Upgrading from the UI** would mean the backend rebuilding and restarting itself mid-request,
  and the admin UI can't safely represent "the server that's about to disappear." A shell script
  run by someone with host access is simpler and fails more predictably; the status page only
  *shows* versions and flags a code/database revision mismatch.
- **`alembic downgrade`** requires every migration to have a correct, tested `down_revision` path,
  which doubles the maintenance burden for a path that's only exercised during an incident.
  Restoring the pre-upgrade backup (above) is the tested, exercised path and always ends in a
  consistent state — the downgrade doesn't need to be logically correct, only the backup does.
