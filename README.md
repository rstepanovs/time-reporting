# Time Reporting

Time tracking with subsequent billing, invoicing and a monthly external-accountant handoff — sized
for a one-person consultancy. Monorepo containing a Python API and a React web client.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| Database | PostgreSQL 17, SQLAlchemy 2.0 (async, asyncpg), Alembic |
| Backend tooling | uv workspace, ruff, mypy (strict), pytest + pytest-asyncio + httpx |
| PDF/spreadsheet rendering | [faktura-printer](https://github.com/rstepanovs/faktura-printer) (invoices), WeasyPrint + Jinja2 (accountant package summary), openpyxl |
| Frontend | React 19, TypeScript, Vite, React Router, Mantine, TanStack Query |
| API client | openapi-typescript + openapi-fetch (types generated from the backend OpenAPI schema) |
| Frontend tooling | npm, ESLint, Vitest + Testing Library |
| Infrastructure | Docker Compose, Dockerfiles per service, GitHub Actions |

## Repository layout

```
.
├── pyproject.toml          # uv workspace root + ruff / mypy / pytest configuration
├── compose.yaml            # db, migrate, backend, frontend
├── .github/workflows/      # CI
├── backend/
│   ├── pyproject.toml      # time-reporting-backend package
│   ├── alembic.ini
│   ├── migrations/         # Alembic environment and revisions
│   ├── src/time_reporting/
│   │   ├── main.py         # FastAPI app factory
│   │   ├── cli.py          # `time-reporting` console script (e.g. create-admin)
│   │   ├── core/           # settings, CQRS bus, password hashing
│   │   ├── db/             # declarative base, engine, sessions
│   │   ├── api/            # root router and shared dependencies (all routes under /api/v1)
│   │   └── modules/        # feature modules (company, users, auth, customers, projects, timesheets, expenses, invoices, accounting, admin, ...), via the CQRS bus — see CLAUDE.md for the full list
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.ts      # dev server proxies /api to the backend
    └── src/
        ├── api/            # typed client, generated schema, query client
        ├── auth/           # session (httpOnly cookie), sign-in / sign-out hooks, route guard
        ├── components/
        ├── pages/
        └── test/
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 automatically)
- Node.js 24 (see `frontend/.nvmrc`)
- Docker with Compose v2
- WeasyPrint's system libraries, for rendering the accountant package's `summary.pdf` (locally and
  in `uv run pytest`, which renders one unstubbed in `test_accounting_handlers.py`): on
  Debian/Ubuntu, `apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
  fonts-dejavu-core` — the same packages `backend/Dockerfile`'s runtime stage installs.

## Getting started

```sh
cp .env.example .env

# Database
docker compose up -d db

# Backend (from the repository root)
uv sync
uv run alembic -c backend/alembic.ini upgrade head
uv run time-reporting create-admin --email you@example.com --name "You"   # first admin account
uv run time-reporting seed-demo   # optional: demo users admin@/manager@/employee@/accountant@/lead@example.com (password demo-password), customers, projects, a company profile, and a sent+issued invoice
uv run uvicorn time_reporting.main:app --reload
# API docs: http://localhost:8000/api/docs

# Frontend
cd frontend
npm install
npm run gen:api   # regenerate src/api/schema.d.ts from the running backend
npm run dev       # http://localhost:5173
```

The first `uv sync` and `npm install` create `uv.lock` and `frontend/package-lock.json`.
Commit both: CI and the Docker builds install strictly from the lock files.

### Full stack in Docker

```sh
docker compose up --build
# Frontend: http://localhost:8080, API: http://localhost:8000/api/docs
```

For a real deployment (upgrading, rolling back, backups/restore, pgAdmin), see
[`docs/operations.md`](docs/operations.md).

## Common commands

Backend (repository root):

```sh
uv run ruff check .            # lint
uv run ruff format .           # format
uv run mypy                    # type check
uv run pytest                  # tests
uv run alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
```

Frontend (`frontend/`):

```sh
npm run lint
npm run typecheck
npm test
npm run build
```
