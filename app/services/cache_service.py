"""
Service de Caching Hybride : Redis (primaire) + In-Memory (fallback gracieux).

Permet de mettre en cache les embeddings vectoriels et les réponses RAG fréquentes
afin de réduire la latence et minimiser les coûts d'appels à l'API Mistral.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Délai avant une nouvelle tentative de connexion après un échec Redis : sans
# réessai, une indisponibilité passagère au démarrage bloquerait le worker sur
# le cache local (non partagé) jusqu'à son redémarrage.
REDIS_RETRY_DELAY_SECONDS = 30.0


class CacheService:
    """Service de cache avec fallback transparent en mémoire si Redis est indisponible."""

    def __init__(self) -> None:
        self._redis_client: Any | None = None
        self._redis_available: bool | None = None  # None = non testé
        self._redis_retry_at: float = 0.0  # prochain essai après un échec
        self._redis_loop: Any | None = None  # event loop propriétaire du client
        self._memory_cache: dict[
            str, tuple[float, str]
        ] = {}  # {key: (expiry_timestamp, value)}

    async def _get_redis(self) -> Any | None:
        """Initialise ou récupère le client Redis asynchrone avec gestion d'erreur."""
        if self._redis_available is False and time.time() < self._redis_retry_at:
            return None

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        # Un client aioredis est lié à l'event loop qui l'a créé : si la boucle
        # a changé (tests, workers), on repart de zéro pour éviter les
        # « Event loop is closed ».
        if self._redis_client is not None and self._redis_loop is not current_loop:
            self._redis_client = None

        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis

                client = aioredis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                    decode_responses=True,
                )
                # Test de connectivité rapide
                await client.ping()
                self._redis_client = client
                self._redis_loop = current_loop
                self._redis_available = True
                logger.info("Connexion au serveur Redis établie avec succès.")
            except Exception as e:
                logger.warning(
                    "Serveur Redis non joignable (%s). Utilisation du cache local en mémoire.",
                    e,
                )
                self._redis_available = False
                self._redis_retry_at = time.time() + REDIS_RETRY_DELAY_SECONDS
                self._redis_client = None
                return None

        return self._redis_client

    def _clean_expired_memory_cache(self) -> None:
        """Nettoie les entrées expirées du cache mémoire local."""
        now = time.time()
        expired_keys = [k for k, (exp, _) in self._memory_cache.items() if exp <= now]
        for k in expired_keys:
            self._memory_cache.pop(k, None)

    @staticmethod
    def _require_shared_backend(key: str) -> None:
        """Refuse un repli local pour les états de sécurité en production."""
        security_prefixes = (
            "prosartisan:security:",
            "prosartisan:revoked_jti:",
            "prosartisan:rate_limit:",
            # Compteurs de quota gratuit : un repli par worker multiplierait
            # le quota journalier par le nombre de workers.
            "prosartisan:quota:",
        )
        if settings.is_production and key.startswith(security_prefixes):
            raise RuntimeError(
                "Redis est indisponible : le stockage de sécurité partagé est requis."
            )

    async def get(self, key: str) -> str | None:
        """Récupère une valeur textuelle depuis Redis ou le cache mémoire."""
        client = await self._get_redis()
        if client is not None:
            try:
                return await client.get(key)
            except Exception as e:
                logger.warning("Erreur lecture Redis pour la clé %s: %s", key, e)

        # Fallback mémoire
        self._require_shared_backend(key)
        self._clean_expired_memory_cache()
        entry = self._memory_cache.get(key)
        if entry:
            exp, val = entry
            if exp > time.time():
                return val
            self._memory_cache.pop(key, None)
        return None

    async def increment(self, key: str, ttl_seconds: int, amount: int = 1) -> int:
        """Incrémente (``amount`` < 0 : décrémente) un compteur avec expiration.

        Retourne sa nouvelle valeur. Utilisé pour le rate limiting en fenêtre
        fixe et les quotas. Redis est primaire (atomique via pipeline
        ``INCRBY`` + ``EXPIRE``) ; sinon compteur en mémoire.
        """
        client = await self._get_redis()
        if client is not None:
            try:
                async with client.pipeline(transaction=True) as pipe:
                    pipe.incrby(key, amount)
                    pipe.expire(key, ttl_seconds)
                    results = await pipe.execute()
                return int(results[0])
            except Exception as e:
                logger.warning("Erreur incrément Redis pour la clé %s: %s", key, e)

        # Fallback mémoire
        self._require_shared_backend(key)
        self._clean_expired_memory_cache()
        now = time.time()
        entry = self._memory_cache.get(key)
        if entry and entry[0] > now:
            count = int(entry[1]) + amount
            self._memory_cache[key] = (entry[0], str(count))
        else:
            count = amount
            self._memory_cache[key] = (now + ttl_seconds, str(count))
        return count

    async def delete(self, key: str) -> None:
        """Supprime une clé de Redis et du cache mémoire."""
        client = await self._get_redis()
        if client is not None:
            try:
                await client.delete(key)
            except Exception as e:
                logger.warning("Erreur suppression Redis pour la clé %s: %s", key, e)
        self._memory_cache.pop(key, None)

    def reset(self) -> None:
        """Vide le cache mémoire local (usage test)."""
        self._memory_cache.clear()

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
        self._require_shared_backend(key)
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

    @classmethod
    def _rag_key(cls, question: str, metier_id: int | None, version: str) -> str:
        # `version` change à chaque (dés)activation de métier/document
        # (voir RAGService.invalidate_activation_cache) : les anciennes
        # réponses deviennent inaccessibles sans parcourir les clés.
        return (
            f"prosartisan:rag:v{version}:{metier_id or 'all'}:"
            f"{cls._hash_text(question)}"
        )

    async def get_cached_rag_response(
        self, question: str, metier_id: int | None = None, version: str = "0"
    ) -> dict[str, Any] | None:
        """Récupère une réponse RAG précédemment générée pour une question identique."""
        key = self._rag_key(question, metier_id, version)
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
        version: str = "0",
    ) -> None:
        """Met en cache une réponse RAG (TTL par défaut 24h)."""
        key = self._rag_key(question, metier_id, version)
        await self.set(key, json.dumps(response), ttl_seconds=ttl_seconds)


cache_service = CacheService()
