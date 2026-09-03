"""
Service de Caching Hybride : Redis (primaire) + In-Memory (fallback gracieux).

Permet de mettre en cache les embeddings vectoriels et les réponses RAG fréquentes
afin de réduire la latence et minimiser les coûts d'appels à l'API OpenAI.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Service de cache avec fallback transparent en mémoire si Redis est indisponible."""

    def __init__(self) -> None:
        self._redis_client: Any | None = None
        self._redis_available: bool | None = None  # None = non testé
        self._memory_cache: dict[str, tuple[float, str]] = {}  # {key: (expiry_timestamp, value)}

    async def _get_redis(self) -> Any | None:
        """Initialise ou récupère le client Redis asynchrone avec gestion d'erreur."""
        if self._redis_available is False:
            return None

        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis

                self._redis_client = aioredis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                    decode_responses=True,
                )
                # Test de connectivité rapide
                await self._redis_client.ping()
                self._redis_available = True
                logger.info("Connexion au serveur Redis établie avec succès.")
            except Exception as e:
                logger.warning(
                    "Serveur Redis non joignable (%s). Utilisation du cache local en mémoire.",
                    e,
                )
                self._redis_available = False
                self._redis_client = None
                return None

        return self._redis_client

    def _clean_expired_memory_cache(self) -> None:
        """Nettoie les entrées expirées du cache mémoire local."""
        now = time.time()
        expired_keys = [k for k, (exp, _) in self._memory_cache.items() if exp <= now]
        for k in expired_keys:
            self._memory_cache.pop(k, None)

    async def get(self, key: str) -> str | None:
        """Récupère une valeur textuelle depuis Redis ou le cache mémoire."""
        client = await self._get_redis()
        if client is not None:
            try:
                return await client.get(key)
            except Exception as e:
                logger.warning("Erreur lecture Redis pour la clé %s: %s", key, e)

        # Fallback mémoire
        self._clean_expired_memory_cache()
        entry = self._memory_cache.get(key)
        if entry:
            exp, val = entry
            if exp > time.time():
                return val
            self._memory_cache.pop(key, None)
        return None

    async def set(self, key: str, value: str, ttl_seconds: int = 3600) -> None:
        """Enregistre une valeur dans Redis ou le cache mémoire avec durée de validité (TTL)."""
        client = await self._get_redis()
        if client is not None:
            try:
                await client.set(key, value, ex=ttl_seconds)
                return
            except Exception as e:
                logger.warning("Erreur écriture Redis pour la clé %s: %s", key, e)

        # Fallback mémoire
        self._clean_expired_memory_cache()
        expiry = time.time() + ttl_seconds
        self._memory_cache[key] = (expiry, value)

    # ── Helpers Métier ──

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()

    async def get_cached_embedding(self, text: str) -> list[float] | None:
        """Récupère un embedding vectoriel précalculé."""
        key = f"prosartisan:emb:{self._hash_text(text)}"
        cached = await self.get(key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass
        return None

    async def cache_embedding(
        self, text: str, embedding: list[float], ttl_seconds: int = 604800
    ) -> None:
        """Met en cache un embedding vectoriel (TTL par défaut 7 jours)."""
        key = f"prosartisan:emb:{self._hash_text(text)}"
        await self.set(key, json.dumps(embedding), ttl_seconds=ttl_seconds)

    async def get_cached_rag_response(
        self, question: str, metier_id: int | None = None
    ) -> dict[str, Any] | None:
        """Récupère une réponse RAG précédemment générée pour une question identique."""
        key = f"prosartisan:rag:{metier_id or 'all'}:{self._hash_text(question)}"
        cached = await self.get(key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass
        return None

    async def cache_rag_response(
        self,
        question: str,
        metier_id: int | None,
        response: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None:
        """Met en cache une réponse RAG (TTL par défaut 24h)."""
        key = f"prosartisan:rag:{metier_id or 'all'}:{self._hash_text(question)}"
        await self.set(key, json.dumps(response), ttl_seconds=ttl_seconds)


cache_service = CacheService()
