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
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.init_db import init_db
from app.db.session import engine
from app.middleware.logging import LoggingAndRequestIdMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware
from app.routers import admin, auth, chat, conversation, health, payment, quota
from app.services.rag_service import rag_service


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise la base de données et la collection Qdrant au démarrage."""
    logging.getLogger("app").info(
        "Démarrage ProsArtisan IA (env=%s) — moteur DB : %s",
        settings.app_env,
        engine.url.get_backend_name(),
    )
    await init_db()
    await rag_service.ensure_collection()
    yield
    await engine.dispose()


app = FastAPI(
    title="ProsArtisan IA Expert",
    description=(
        "API de l'assistant IA dédié aux artisans professionnels. "
        "Fournit des réponses techniques via RAG, gère les quotas freemium "
        "et les paiements Mobile Money (Wave, Orange, MTN, Moov)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── Logging et Request ID Middleware ──
app.add_middleware(LoggingAndRequestIdMiddleware)

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

# ── Routers ──
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(conversation.router)
app.include_router(payment.router)
app.include_router(quota.router)
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
