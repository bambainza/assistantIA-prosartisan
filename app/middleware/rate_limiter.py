import time
from collections import defaultdict
from typing import ClassVar

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware pour limiter le débit des requêtes (Rate Limiting)."""

    # Attribut de classe pour permettre aux tests unitaires de purger l'historique
    history: ClassVar[defaultdict[str, list[float]]] = defaultdict(list)

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Protéger les routes sensibles (Authentification et Chat/Streaming)
        if path.startswith(("/api/chat", "/api/auth")):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()

            # Nettoyer l'historique des requêtes datant de plus d'une minute
            self.history[client_ip] = [
                t for t in self.history[client_ip] if now - t < 60
            ]

            # Évaluation dynamique de la limite
            limit = self.requests_per_minute or settings.rate_limit_requests_per_minute

            if len(self.history[client_ip]) >= limit:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Trop de requêtes. Veuillez patienter une minute avant de réessayer."
                    },
                )

            self.history[client_ip].append(now)

        return await call_next(request)
