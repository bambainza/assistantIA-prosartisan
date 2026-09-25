"""Middleware de limitation de débit (Rate Limiting) adossé à Redis.

Fenêtre fixe d'une minute par IP cliente sur les routes sensibles
(`/api/chat`, `/api/auth`). Le compteur est stocké dans Redis (partagé entre
tous les workers). Hors production, repli automatique sur un compteur en
mémoire si Redis est indisponible ; en production, le préfixe
`prosartisan:rate_limit:` interdit ce repli (voir
`CacheService._require_shared_backend`) et le trafic passe sans limite plutôt
que d'être bloqué.

L'IP cliente est résolue via `get_client_ip` (prise en compte des reverse
proxies de confiance, `TRUSTED_PROXY_HOPS`). Les WebSockets ne traversent pas
ce middleware HTTP : `chat_websocket_endpoint` appelle `is_rate_limited` à
chaque message.
"""

import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.middleware.client_ip import get_client_ip
from app.services.cache_service import cache_service

# Durée de la fenêtre de comptage, en secondes.
WINDOW_SECONDS = 60

RATE_LIMIT_MESSAGE = (
    "Trop de requêtes. Veuillez patienter une minute avant de réessayer."
)


async def is_rate_limited(client_ip: str, limit: int | None = None) -> bool:
    """Incrémente le compteur de la minute courante et indique si la limite est dépassée."""
    limit = limit or settings.rate_limit_requests_per_minute

    # Clé horodatée : la fenêtre se réinitialise seule à chaque minute.
    window = int(time.time() // WINDOW_SECONDS)
    key = f"prosartisan:rate_limit:{client_ip}:{window}"

    try:
        count = await cache_service.increment(key, WINDOW_SECONDS)
    except Exception:
        # Ne jamais bloquer le trafic si le backend de comptage échoue.
        count = 0

    return count > limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware pour limiter le débit des requêtes (Rate Limiting)."""

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute

    async def dispatch(self, request: Request, call_next):
        # Protéger les routes sensibles (Authentification et Chat/Streaming)
        route_sensible = request.url.path.startswith(("/api/chat", "/api/auth"))
        if route_sensible and await is_rate_limited(
            get_client_ip(request), self.requests_per_minute
        ):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": RATE_LIMIT_MESSAGE},
            )

        return await call_next(request)
