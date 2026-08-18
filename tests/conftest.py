"""Fixtures partagées pour pytest."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app


async def mock_get_db():
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=None))
            ),
        )
    )
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    yield session


app.dependency_overrides[get_db] = mock_get_db


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Client HTTP async pour tester les routes FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
