# syntax=docker/dockerfile:1
# Build context: repository root (the uv workspace lives there).

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Third-party dependencies first, so this layer is reused until the lock file changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/pyproject.toml,target=backend/pyproject.toml \
    uv sync --locked --no-dev --no-install-workspace --package time-reporting-backend

COPY pyproject.toml uv.lock ./
COPY backend ./backend

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package time-reporting-backend


FROM python:3.13-slim-bookworm

ARG GIT_SHA

# Debian bookworm ships only PostgreSQL 15's client, which can't `pg_dump`/`pg_restore` against a
# 17 server (`db`'s image, compose.yaml) — pull `postgresql-client-17` from the PGDG apt repo
# instead.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app backend/alembic.ini backend/alembic.ini
COPY --chown=app:app backend/migrations backend/migrations

# `compose.yaml` mounts the `backups`/`attachments` named volumes here; a directory owned by `app`
# must already exist in the image, otherwise Docker initializes the empty volume as root-owned and
# `app` can't write to it.
RUN mkdir -p /var/backups/time-reporting /var/lib/time-reporting/attachments \
    && chown -R app:app /var/backups/time-reporting /var/lib/time-reporting

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_GIT_SHA=$GIT_SHA

USER app

EXPOSE 8000

CMD ["uvicorn", "time_reporting.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
