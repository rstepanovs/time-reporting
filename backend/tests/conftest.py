import os
from collections.abc import AsyncIterator
from uuid import UUID

# Settings are read at import time (module-level get_settings() calls, e.g. db/session.py), so the
# secret must be set before anything under time_reporting is imported.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-do-not-use-in-production-0000000")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from support import (
    DEFAULT_BILLING_ADDRESS,
    DEFAULT_BILLING_PERIOD,
    DEFAULT_PASSWORD,
    EMPLOYEE,
    AuthHeaders,
    CustomerFactory,
    ProjectFactory,
    UserFactory,
)
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.db.session import get_session
from time_reporting.main import create_app
from time_reporting.modules.auth.jwt import create_access_token
from time_reporting.modules.customers.contracts import CreateCustomer, CustomerDTO
from time_reporting.modules.projects.contracts import CreateProject, ProjectDTO
from time_reporting.modules.registry import build_registry
from time_reporting.modules.users.contracts import CreateUser, UserDTO, UserRole


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session bound to a connection whose outer transaction is rolled back after the test.

    Requires a running, migrated database (as CI and local dev already provide). ``NullPool``
    keeps each test on its own connection, independent of the app's pooled engine.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def bus(db_session: AsyncSession) -> Bus:
    return Bus(build_registry(), db_session)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    # HTTPS, so the client's cookie jar sends back the `Secure` session cookie.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        yield client


@pytest.fixture
def make_user(bus: Bus) -> UserFactory:
    created = 0

    async def factory(
        *,
        roles: frozenset[UserRole] = EMPLOYEE,
        email: str | None = None,
        name: str = "Test User",
        password: str = DEFAULT_PASSWORD,
    ) -> UserDTO:
        nonlocal created
        created += 1
        return await bus.execute(
            CreateUser(
                name=name,
                email=email or f"user{created}@example.com",
                roles=roles,
                password=password,
            )
        )

    return factory


@pytest.fixture
def make_customer(bus: Bus) -> CustomerFactory:
    created = 0

    async def factory(*, name: str | None = None) -> CustomerDTO:
        nonlocal created
        created += 1
        return await bus.execute(
            CreateCustomer(
                name=name or f"Customer {created}",
                billing_address=DEFAULT_BILLING_ADDRESS,
                billing_period=DEFAULT_BILLING_PERIOD,
                currency="EUR",
            )
        )

    return factory


@pytest.fixture
def make_project(bus: Bus, make_customer: CustomerFactory) -> ProjectFactory:
    created = 0

    async def factory(
        *,
        customer_id: UUID | None = None,
        name: str | None = None,
        description: str | None = None,
        is_internal: bool = False,
        manager_id: UUID | None = None,
    ) -> ProjectDTO:
        nonlocal created
        created += 1
        if customer_id is None:
            customer_id = (await make_customer()).id
        return await bus.execute(
            CreateProject(
                customer_id=customer_id,
                name=name or f"Project {created}",
                description=description,
                is_internal=is_internal,
                manager_id=manager_id,
            )
        )

    return factory


@pytest.fixture
def auth_headers() -> AuthHeaders:
    def build(user: UserDTO) -> dict[str, str]:
        token = create_access_token(user.id, token_version=user.token_version)
        return {"Authorization": f"Bearer {token.token}"}

    return build
