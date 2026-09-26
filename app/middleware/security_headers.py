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

# Les scripts et attributs événementiels inline sont interdits.
_CSP_SCRIPT_SRC = (
    "script-src 'self' "
    "https://accounts.google.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com"
)
_CSP_DIRECTIVES = (
    "default-src 'self'",
    "img-src 'self' data: blob:",
    # Polices Google (chat_web, thème Dastone de l'admin) et thème highlight.js.
    (
        "style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com https://cdnjs.cloudflare.com"
    ),
    "font-src 'self' data: https://fonts.gstatic.com",
    _CSP_SCRIPT_SRC,
    "script-src-attr 'none'",
    "connect-src 'self' https://accounts.google.com",
    "frame-src https://accounts.google.com",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
)
_CONTENT_SECURITY_POLICY = "; ".join(_CSP_DIRECTIVES)
_ADMIN_CONTENT_SECURITY_POLICY = _CONTENT_SECURITY_POLICY.replace(
    "script-src-attr 'none'", "script-src-attr 'unsafe-inline'"
)


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
        response.headers["Content-Security-Policy"] = (
            _ADMIN_CONTENT_SECURITY_POLICY
            if request.url.path.startswith("/admin")
            else _CONTENT_SECURITY_POLICY
        )

        if settings.is_production:
            # HSTS n'a de sens que derrière HTTPS (systématique en production).
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )

        return response
