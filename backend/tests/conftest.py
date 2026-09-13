from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from time_reporting.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
