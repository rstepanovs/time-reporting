#!/usr/bin/env bash
# Upgrades a Docker Compose deployment: check out a ref (or pull the current branch), rebuild the
# images, apply migrations (which back up the database first) and restart the stack.
#
# Usage: scripts/upgrade.sh [ref]
#   ref   A branch, tag or commit to check out. Defaults to fast-forwarding the current branch.
#
# See docs/operations.md for the full runbook, including rollback.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree is not clean; commit, stash or discard changes before upgrading" >&2
  exit 1
fi

if [[ $# -ge 1 ]]; then
  git fetch --all --tags
  git checkout "$1"
else
  git pull --ff-only
fi

export GIT_SHA
GIT_SHA="$(git rev-parse --short HEAD)"

docker compose build
# Backs up (unless the database isn't migrated yet or is already at head) and applies pending
# migrations; run explicitly first so a failure here stops the script before anything restarts.
docker compose run --rm migrate
docker compose up -d

echo "Upgraded to ${GIT_SHA}."
