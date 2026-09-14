# Plan: users module + JWT authentication with CQRS between modules (time-reporting backend)

## Context

`time-reporting/backend` is a FastAPI scaffold (async SQLAlchemy + asyncpg, Alembic, pydantic-settings)
with only a health-check endpoint and no domain models. The API needs authentication before
domain features (projects, time entries, invoices) are added. We add:

- a lightweight in-process **CQRS bus** (commands / queries + handlers) — the only way feature
  modules talk to each other;
- a **users** feature module: ORM model, repository, service, command/query handlers, public
  contracts, admin CRUD + `/users/me`;
- a separate **auth** feature module: JWT access tokens, login endpoint, `get_current_user` /
  `require_roles(...)` dependencies — it reaches user data only through the bus;
- a CLI command to bootstrap the first administrator (no self-registration).

Decisions confirmed with the user: feature modules under `time_reporting/modules/`; users are
created by an admin (first admin via CLI); **access token only** (no refresh); admin CRUD + `/me`;
**CQRS as an inter-module bus** (single DB and model, no separate read models); **own bus
implementation** (no third-party mediator library).

## New dependencies (`backend/pyproject.toml`)

- `pyjwt>=2.14` — JWT encode/decode (HS256)
- `pwdlib[argon2]>=0.3.1` — Argon2id hashing (passlib is unmaintained; bcrypt has a 72-byte limit)
- `email-validator>=2.3` — `EmailStr`
- `python-multipart>=0.0.32` — required by `OAuth2PasswordRequestForm` (Swagger "Authorize" button)

Run `uv lock` / `uv sync` so `uv.lock` is updated (CI and Docker install with `--locked`).

## Layout

```
backend/src/time_reporting/
  core/
    config.py               # + JWT settings
    cqrs.py                 # NEW: Command/Query bases, handler protocols, HandlerRegistry, Bus
    passwords.py            # NEW: shared password hashing (used by users; not owned by a module)
  db/mixins.py              # NEW: TimestampMixin (created_at, updated_at)
  models/__init__.py        # + import modules.users.models (Alembic metadata registry)
  api/deps.py               # + BusDep
  api/router.py             # + include auth.router, users.router
  main.py                   # build HandlerRegistry at startup, store in app.state
  cli.py                    # NEW: `time-reporting create-admin`
  modules/
    __init__.py             # build_registry(): calls every module's register()
    users/
      contracts.py          # PUBLIC: UserRole, DTOs, commands, queries, domain exceptions
      models.py  repository.py  service.py  handlers.py  module.py
      schemas.py  router.py
    auth/
      jwt.py  service.py  exceptions.py  schemas.py
      dependencies.py       # PUBLIC (HTTP guards): CurrentUserDep, require_roles, AdminDep
      router.py
```

### Module boundary rule

A module may import from another module **only** its `contracts.py`, plus `auth.dependencies`
(the HTTP guards every router needs). `core/`, `db/`, `api/deps.py` are shared kernel. Enforced by
`tests/test_module_boundaries.py` (walks `modules/**/*.py` with `ast`, fails on any other
`time_reporting.modules.<other>.*` import). Documented in `CLAUDE.md`.

## CQRS bus (`core/cqrs.py`)

```python
@dataclass(frozen=True)
class Command[R]: ...          # message that changes state, result type R

@dataclass(frozen=True)
class Query[R]: ...            # read-only message, result type R

class CommandHandler[C: Command[Any], R](Protocol):
    async def handle(self, message: C) -> R: ...
class QueryHandler[Q: Query[Any], R](Protocol): ...

type HandlerFactory = Callable[[Bus], CommandHandler[Any, Any] | QueryHandler[Any, Any]]

class HandlerRegistry:
    def command(self, message_type, factory) -> None   # DuplicateHandlerError on re-registration
    def query(self, message_type, factory) -> None
    def freeze(self) -> None                            # no registration after startup

class Bus:
    def __init__(self, registry: HandlerRegistry, session: AsyncSession) -> None
    session: AsyncSession                               # handlers take the session from the bus
    async def execute[R](self, command: Command[R]) -> R
    async def query[R](self, query: Query[R]) -> R
```

- Concrete messages subclass with the result type, e.g.
  `class GetUserById(Query[UserDTO | None])`, so `await bus.query(GetUserById(id))` is typed as
  `UserDTO | None` under mypy strict.
- Lookup by exact `type(message)`; unknown message → `HandlerNotFoundError`. Commands passed to
  `query()` (and vice versa) are rejected.
- **Transactions**: one `AsyncSession` per request, shared by all handlers through the bus.
  `execute()` tracks nesting depth: the outermost command commits on success and rolls back on
  exception; nested commands and all queries never commit. Services/repositories only `flush()`.
- Factories receive the `Bus` so a handler can dispatch further messages to other modules.
- Wiring: each module exposes `module.py: register(registry)`; `modules.build_registry()` calls
  them; `create_app()` stores the frozen registry in `app.state.handlers`.
  `api/deps.py`: `get_bus(request, session) -> Bus`, `BusDep = Annotated[Bus, Depends(get_bus)]`.
  CLI builds a `Bus` from `build_registry()` + `SessionFactory()`.

## Shared kernel additions

- **`core/passwords.py`**: `PasswordHash((Argon2Hasher(),))`; `hash_password`,
  `verify_password(password, hash) -> (ok, updated_hash | None)` (via `verify_and_update`),
  `verify_dummy()` to equalize timing when an email doesn't exist.
- **`db/mixins.py` — `TimestampMixin`**: `created_at`, `updated_at` as `DateTime(timezone=True)`,
  `server_default=func.now()`, `updated_at` with `onupdate=func.now()`.
- **`core/config.py`**: `jwt_secret_key: SecretStr` (**required**, `min_length=32`),
  `jwt_algorithm: str = "HS256"`, `access_token_expire_minutes: int = 60`. Add `JWT_SECRET_KEY`
  (+ hint `openssl rand -hex 32`) to `.env.example`, `x-backend-env` in `compose.yaml`
  (`${JWT_SECRET_KEY:?set JWT_SECRET_KEY in .env}`), backend job env in `.github/workflows/ci.yml`,
  and a generated value to the local (gitignored) `.env`.

## Users module

**`contracts.py` (public API of the module)**
- `UserRole(StrEnum)`: `ADMIN="admin"`, `PROJECT_MANAGER="project_manager"`, `WORKER="worker"`
- DTOs (frozen dataclasses, never ORM objects):
  `UserDTO(id, name, email, role, is_active, token_version, last_login_at, created_at, updated_at)`,
  `UserCredentialsDTO(id, password_hash, is_active)`, `UserPageDTO(items, total, limit, offset)`
- Queries: `GetUserById(user_id) -> UserDTO | None`,
  `GetUserCredentialsByEmail(email) -> UserCredentialsDTO | None`,
  `ListUsers(limit, offset) -> UserPageDTO`
- Commands: `CreateUser(name, email, role, password) -> UserDTO`,
  `UpdateUser(user_id, acting_user_id, name?, email?, role?, is_active?) -> UserDTO`
  (unset fields via a sentinel / `fields_set`),
  `ResetUserPassword(user_id, new_password) -> None`,
  `ChangeOwnPassword(user_id, current_password, new_password) -> None`,
  `RecordSuccessfulLogin(user_id, rehashed_password_hash: str | None) -> None`
- Exceptions: `UserNotFoundError`, `EmailAlreadyExistsError`, `SelfModificationError`,
  `InvalidCurrentPasswordError`

**`models.py`** — `User(TimestampMixin, Base)`, table `users` (imports `UserRole` from contracts):
- `id: UUID` PK (default `uuid.uuid4`), `name: String(255)`, `email: String(320)` unique (lower-cased),
  `role: Enum(UserRole, name="user_role", values_callable=...)`, `password_hash: String(255)`
- service fields: `is_active` (server default true), `token_version: int` (server default 0; put in
  the JWT, bumped on password change/reset → invalidates issued tokens), `last_login_at` (nullable),
  `created_at`, `updated_at`
- No hard delete (future time entries will reference users) — deactivate via `is_active`.

**`repository.py` — `UserRepository(session)`**: `get_by_id`, `get_by_email` (normalizes case),
`list(limit, offset)`, `count()`, `add(user)` (flush; `IntegrityError` on the email constraint →
`EmailAlreadyExistsError`), `flush()`. Never commits.

**`service.py` — `UserService(session)`**: domain logic on ORM entities — `create_user`,
`update_user` (an admin may not change their own role or deactivate themselves →
`SelfModificationError`; email conflict → `EmailAlreadyExistsError`), `reset_password`
(hash + `token_version += 1`), `change_own_password` (verify current first), `record_login`
(`last_login_at = now()`, store rehash if given). Flushes only — the bus commits.

**`handlers.py`**: one small class per message (`CreateUserHandler`, `GetUserByIdHandler`, ...),
each built from the bus session, delegating to `UserService` / `UserRepository` and mapping
entities to DTOs (`to_dto(user)`). **`module.py`**: `register(registry)` wires all of them.

**`schemas.py`** (HTTP only): `UserCreateRequest` (password 8–128), `UserUpdateRequest`
(all optional, `extra="forbid"`), `PasswordChangeRequest`, `PasswordResetRequest`,
`UserResponse` (`from_attributes`, built from `UserDTO`; no hash/token_version), `UserPageResponse`.
Emails lower-cased in a validator.

**`router.py`** (prefix `/users`, tag `users`) — thin: request schema → command/query via `BusDep`
→ response schema; contract exceptions → `HTTPException`.

| Method | Path | Access | Message | Result |
|---|---|---|---|---|
| GET | `/users/me` | authenticated | (current user) | `UserResponse` |
| POST | `/users/me/password` | authenticated | `ChangeOwnPassword` | 204 / 400 wrong current |
| GET | `/users?limit&offset` | admin | `ListUsers` | `UserPageResponse` |
| POST | `/users` | admin | `CreateUser` | 201 / 409 duplicate email |
| GET | `/users/{user_id}` | admin | `GetUserById` | `UserResponse` / 404 |
| PATCH | `/users/{user_id}` | admin | `UpdateUser` | 200 / 404 / 409 / 400 self-modification |
| PUT | `/users/{user_id}/password` | admin | `ResetUserPassword` | 204 / 404 |

## Auth module (depends on users only via `users.contracts`)

- **`jwt.py`**: `create_access_token(user: UserDTO) -> (token, expires_in)` with claims `sub`
  (user id), `ver` (token_version), `iat`, `exp`; `decode_access_token(token) -> TokenPayload`
  (PyJWT `options={"require": [...]}`), raising `InvalidTokenError`.
- **`exceptions.py`**: `InvalidCredentialsError`, `InvalidTokenError`.
- **`service.py` — `AuthService(bus)`**:
  `login(email, password) -> TokenResponse`:
  1. `bus.query(GetUserCredentialsByEmail(email))`; missing → `verify_dummy()` + `InvalidCredentialsError`
  2. `verify_password`; wrong password or `is_active=False` → same `InvalidCredentialsError`
  3. `bus.execute(RecordSuccessfulLogin(id, rehashed_hash))` (top-level → committed)
  4. `bus.query(GetUserById(id))` → `create_access_token`
- **`schemas.py`**: `TokenResponse(access_token, token_type="bearer", expires_in)`, `TokenPayload`.
- **`dependencies.py`**:
  - `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")`
  - `get_current_user(token, bus) -> UserDTO` — decode → `bus.query(GetUserById)` → reject if
    missing, inactive, or `ver != token_version` → 401 with `WWW-Authenticate: Bearer`;
    `CurrentUserDep = Annotated[UserDTO, Depends(get_current_user)]`
  - `require_roles(*roles: UserRole)` → 403 otherwise;
    `AdminDep = Annotated[UserDTO, Depends(require_roles(UserRole.ADMIN))]`
- **`router.py`** (prefix `/auth`): `POST /auth/login` with `OAuth2PasswordRequestForm`
  (`username` = email) → `TokenResponse`; 401 on bad credentials.

Role and active status are always read from the DB on each request (not trusted from the token),
so role changes and deactivation take effect immediately.

## Migration

`uv run alembic -c backend/alembic.ini revision --autogenerate -m "create users table"`, then review:
add `sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)` after `op.drop_table("users")`
in `downgrade()` (autogenerate doesn't drop PG enums).

## CLI (`cli.py`)

`argparse` + `asyncio.run`: `create-admin --email --name`, password via `getpass` or
`--password-stdin`. Builds a `Bus` and runs `CreateUser(..., role=UserRole.ADMIN)`; prints a clear
error on `EmailAlreadyExistsError`. Exposed as `[project.scripts] time-reporting = "time_reporting.cli:main"`
→ `uv run time-reporting create-admin ...` / `docker compose run --rm backend time-reporting create-admin ...`.

## Tests (`backend/tests/`)

- `conftest.py`: `os.environ.setdefault("JWT_SECRET_KEY", ...)` before app imports; `db_session`
  — per-test `NullPool` engine, outer transaction, `AsyncSession(bind=conn,
  join_transaction_mode="create_savepoint")`, rolled back after the test (needs a migrated DB, as
  CI already does); `bus` fixture (`build_registry()` + `db_session`); `client` overriding
  `get_session`; `make_user(role=...)` factory (via `CreateUser`) and `auth_headers(user)`.
- `test_cqrs.py` — fake messages/handlers: typed dispatch, `HandlerNotFoundError`,
  `DuplicateHandlerError`, top-level command commits / rolls back on error, nested command and
  queries don't commit, registration after `freeze()` fails.
- `test_module_boundaries.py` — the import rule above.
- `test_passwords.py`, `test_jwt.py` — hash/verify/rehash, expired token, bad signature, missing claims.
- `test_users_handlers.py` — commands/queries through the bus (create, duplicate email, update,
  self-modification, password reset bumps `token_version`, list paging).
- `test_auth.py` — login success; wrong password / unknown email / inactive → identical 401;
  missing / garbage token → 401; token rejected after password change and after deactivation.
- `test_users_api.py` — admin CRUD; worker & project manager → 403; `/users/me`; own password change.
- `test_cli.py` — create-admin path via the bus.

## Docs

Update `CLAUDE.md` (architecture: `modules/` layout, CQRS bus & transaction rule, module boundary
rule, auth dependencies, CLI, `JWT_SECRET_KEY`, tests need migrated Postgres) and `README.md`
(layout, creating the first admin). Frontend out of scope.

## Verification

From `time-reporting/` (Postgres from `docker compose up -d db` is already running):
1. `uv sync` → `uv run alembic -c backend/alembic.ini upgrade head`, then `downgrade -1` and `upgrade head`
2. `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
3. Manual smoke test: `uv run time-reporting create-admin --email admin@example.com --name Admin`,
   `uv run uvicorn time_reporting.main:app`, "Authorize" in `/api/docs`, `GET /api/v1/users/me`,
   create a worker via `POST /users`, log in as the worker and confirm `GET /users` → 403.
