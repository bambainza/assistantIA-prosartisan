"""Middleware d'en-têtes de sécurité HTTP (défense en profondeur navigateur).

Complète le rate limiting et le CORS déjà en place : ces en-têtes réduisent la
surface d'attaque côté navigateur (clickjacking, sniffing MIME, fuite de
referrer, XSS via ressources tierces non autorisées) sans dépendre du code
métier de chaque route.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings

# Les blocs <script> inline sont interdits. Les attributs événementiels hérités
# restent temporairement autorisés séparément, le temps de leur migration vers
# addEventListener, sans autoriser pour autant l'injection de nouveaux scripts.
_CSP_SCRIPT_SRC = (
    "script-src 'self' "
    "https://accounts.google.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com"
)
_CSP_DIRECTIVES = (
    "default-src 'self'",
    "img-src 'self' data: blob:",
    "style-src 'self' 'unsafe-inline'",
    _CSP_SCRIPT_SRC,
    "script-src-attr 'unsafe-inline'",
    "connect-src 'self' https://accounts.google.com",
    "frame-src https://accounts.google.com",
    "frame-ancestors 'none'",
)
_CONTENT_SECURITY_POLICY = "; ".join(_CSP_DIRECTIVES)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les en-têtes de sécurité recommandés à chaque réponse HTTP."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(self), microphone=(self), geolocation=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY

        if settings.is_production:
            # HSTS n'a de sens que derrière HTTPS (systématique en production).
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )

        return response
