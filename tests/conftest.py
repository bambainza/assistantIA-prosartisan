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


@pytest.fixture(autouse=True)
def _isoler_cache():
    """Force le cache/rate-limiter en mémoire et le réinitialise entre les tests.

    La suite doit rester déterministe même si un Redis local tourne (Docker) :
    on ne veut ni dépendre de son état ni le polluer.
    """
    from app.services.cache_service import cache_service

    cache_service._redis_available = False
    cache_service._redis_client = None
    cache_service.reset()
    yield
    cache_service.reset()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Client HTTP async pour tester les routes FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
