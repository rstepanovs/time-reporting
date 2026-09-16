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

`compose.yaml` brings the stack up in dependency order: `db` → `migrate` (creates the schema, since
there's nothing to back up yet) → `backend`/`backup` → `frontend`. Create the first administrator
once the backend is up:

```sh
docker compose exec backend time-reporting create-admin --email you@example.com --name "You"
```

Frontend: `http://<host>:8080`. API docs: `http://<host>:8000/api/docs`.

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

## Restore

`time-reporting restore <file> --yes` (`pg_restore --clean --if-exists --single-transaction
--no-owner`) replaces the current database's contents with the backup's. It is **CLI-only**,
deliberately not exposed over HTTP or from the admin UI — see [Rollback](#rollback) for the full
sequence (stop `backend` first, so nothing writes mid-restore). Without `--yes` it refuses to run.
The command also prints the alembic revision recorded in the backup's file name, so you can
confirm it matches the code you're about to run before continuing.

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
