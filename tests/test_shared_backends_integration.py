"""Contrats Redis réels, activés en CI ou avec RUN_SHARED_BACKEND_TESTS=1."""

import asyncio
import os
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as redis

from app.config import settings
from app.services.cache_service import CacheService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SHARED_BACKEND_TESTS") != "1",
    reason="Nécessite un Redis réel explicitement sélectionné.",
)


@pytest.mark.parametrize("operation", ["rotation", "budget"])
async def test_reservations_atomiques_entre_clients_redis(
    monkeypatch: pytest.MonkeyPatch, operation: Any
) -> None:
    # Deux connexions simulent deux workers, sans toucher aux compteurs métier.
    clients = [
        redis.from_url(settings.redis_url, decode_responses=True) for _ in range(2)
    ]
    caches = [CacheService(), CacheService()]
    key = f"prosartisan:quota:integration:{uuid.uuid4()}"
    for cache, client in zip(caches, clients, strict=True):
        monkeypatch.setattr(cache, "_get_redis", AsyncMock(return_value=client))
    try:
        await clients[0].ping()
        if operation == "rotation":
            results = await asyncio.gather(
                *[caches[i % 2].set_if_absent(key, "1", 60) for i in range(20)]
            )
            assert sum(results) == 1
        else:
            results = await asyncio.gather(
                *[caches[i % 2].reserve_budget(key, 1, 5, 60) for i in range(20)]
            )
            assert sum(results) == 5
            assert int(await clients[0].get(key)) == 5
            await caches[0].increment(key, 60, amount=-1)
            assert await caches[1].reserve_budget(key, 1, 5, 60)
        assert 0 < await clients[0].ttl(key) <= 60
    finally:
        await clients[0].delete(key)
        for client in clients:
            await client.aclose()
