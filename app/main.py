"""
ProsArtisan IA Expert — Point d'entrée FastAPI.

Assistant IA conversationnel pour artisans professionnels.
Architecture RAG + Freemium + Mobile Money.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.init_db import init_db
from app.db.session import engine
from app.middleware.logging import LoggingAndRequestIdMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import (
    actualite,
    admin,
    auth,
    chat,
    conversation,
    finance,
    health,
    media,
    notification,
    parametres,
    payment,
    quota,
    quote,
)
from app.services.media_service import ImageInvalideError
from app.services.quota_service import QuotaIndisponibleError
from app.services.rag_service import rag_service


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise la base de données et la collection Qdrant au démarrage, nettoie à l'arrêt."""
    logging.getLogger("app").info(
        "Démarrage ProsArtisan IA (env=%s) — moteur DB : %s",
        settings.app_env,
        engine.url.get_backend_name(),
    )
    await init_db()
    await rag_service.ensure_collection()
    yield
    await engine.dispose()


def docs_urls(is_production: bool) -> tuple[str | None, str | None, str | None]:
    """Retourne (docs_url, redoc_url, openapi_url) — masqués en production.

    Swagger UI/ReDoc exposent le détail complet de l'API (schémas, routes
    internes) : en production, seule une lecture directe de `openapi.json`
    par un tiers autorisé a du sens, jamais l'UI interactive publique.
    """
    if is_production:
        return None, None, None
    return "/docs", "/redoc", "/openapi.json"


_docs_url, _redoc_url, _openapi_url = docs_urls(settings.is_production)

app = FastAPI(
    title="ProsArtisan IA Expert",
    description=(
        "API de l'assistant IA dédié aux artisans professionnels. "
        "Fournit des réponses techniques via RAG, gère les quotas freemium "
        "et les paiements Mobile Money (Wave, Orange Money)."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# ── Logging et Request ID Middleware ──
app.add_middleware(LoggingAndRequestIdMiddleware)

# ── En-têtes de sécurité HTTP (CSP, HSTS, X-Frame-Options...) ──
app.add_middleware(SecurityHeadersMiddleware)

# ── Rate Limiting Middleware ──
app.add_middleware(RateLimitMiddleware)

# ── CORS Restreint ──
cors_origins = (
    [
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]
    if settings.cors_allowed_origins != "*"
    else ["*"]
)

# Le couple allow_origins=["*"] + allow_credentials=True est rejeté par les
# navigateurs : on n'active les credentials que si une liste blanche est définie.
allow_credentials = cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(QuotaIndisponibleError)
async def quota_indisponible_handler(
    request: Request, exc: QuotaIndisponibleError
) -> JSONResponse:
    """Compteur de quota (Redis) injoignable : 503 plutôt qu'un quota faussé."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Service momentanément indisponible. Réessayez dans un instant."
        },
    )


@app.exception_handler(ImageInvalideError)
async def image_invalide_handler(
    request: Request, exc: ImageInvalideError
) -> JSONResponse:
    """Photo de chantier refusée avant tout décompte de quota."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ── Routers ──
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(conversation.router)
app.include_router(payment.router)
app.include_router(quota.router)
app.include_router(notification.router)
app.include_router(actualite.router)
app.include_router(finance.router)
app.include_router(quote.router)
app.include_router(parametres.router)
app.include_router(media.router)
app.include_router(admin.router)

# ── Back-Office Admin Frontend ──
admin_web_dir = os.path.join(os.path.dirname(__file__), "..", "admin_web")
if os.path.exists(admin_web_dir):
    app.mount("/admin", StaticFiles(directory=admin_web_dir, html=True), name="admin")

# ── Front-Office Chat Frontend ──
chat_web_dir = os.path.join(os.path.dirname(__file__), "..", "chat_web")
if os.path.exists(chat_web_dir):
    app.mount("/chat", StaticFiles(directory=chat_web_dir, html=True), name="chat")


@app.get("/", tags=["Root"])
async def root(request: Request):
    """Page d'accueil de l'API (Redirige vers /chat/ si demandé par un navigateur)."""
    accept = request.headers.get("accept")
    if accept and "text/html" in accept:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/chat/")
    return {
        "message": "Bienvenue sur l'API ProsArtisan IA Expert 🚀",
        "docs": "/docs",
        "health": "/health",
    }
