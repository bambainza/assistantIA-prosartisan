"""Protection CSRF des sessions navigateur authentifiées par cookie."""

from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.middleware.auth import CSRF_COOKIE, WEB_ACCESS_COOKIE


class CSRFMiddleware(BaseHTTPMiddleware):
    """Exige un double-submit token pour toute mutation de session Web.

    Les clients mobiles utilisant explicitement ``Authorization: Bearer`` ne
    sont pas concernés et conservent leur contrat actuel.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            if request.url.path in {"/api/auth/web/login", "/api/auth/web/google"}:
                return await call_next(request)
            web_session = request.cookies.get(WEB_ACCESS_COOKIE)
            bearer = request.headers.get("authorization", "").startswith("Bearer ")
            if web_session and not bearer:
                cookie_token = request.cookies.get(CSRF_COOKIE)
                header_token = request.headers.get("x-csrf-token")
                if (
                    not cookie_token
                    or not header_token
                    or not secrets.compare_digest(cookie_token, header_token)
                ):
                    return JSONResponse(
                        {"detail": "Jeton CSRF absent ou invalide."}, status_code=403
                    )
        return await call_next(request)
