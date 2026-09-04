"""Middleware de limitation de débit (Rate Limiting) adossé à Redis.

Fenêtre fixe d'une minute par IP cliente sur les routes sensibles
(`/api/chat`, `/api/auth`). Le compteur est stocké dans Redis (partagé entre
tous les workers) avec repli automatique sur un compteur en mémoire si Redis
est indisponible.
"""

import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.services.cache_service import cache_service

# Durée de la fenêtre de comptage, en secondes.
WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware pour limiter le débit des requêtes (Rate Limiting)."""

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Protéger les routes sensibles (Authentification et Chat/Streaming)
        if path.startswith(("/api/chat", "/api/auth")):
            client_ip = request.client.host if request.client else "unknown"
            limit = self.requests_per_minute or settings.rate_limit_requests_per_minute

            # Clé horodatée : la fenêtre se réinitialise seule à chaque minute.
            window = int(time.time() // WINDOW_SECONDS)
            key = f"prosartisan:rl:{client_ip}:{window}"

            try:
                count = await cache_service.increment(key, WINDOW_SECONDS)
            except Exception:
                # Ne jamais bloquer le trafic si le backend de comptage échoue.
                count = 0

            if count > limit:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Trop de requêtes. Veuillez patienter une minute avant de réessayer."
                    },
                )

        return await call_next(request)
