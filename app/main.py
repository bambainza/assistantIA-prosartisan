"""
ProsArtisan IA Expert — Point d'entrée FastAPI.

Assistant IA conversationnel pour artisans professionnels.
Architecture RAG + Freemium + Mobile Money.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.init_db import init_db
from app.routers import admin, chat, health, payment, quota


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise la base de données au démarrage, nettoie à l'arrêt."""
    await init_db()
    yield


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

# ── CORS (autoriser l'app mobile Flutter) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(payment.router)
app.include_router(quota.router)
app.include_router(admin.router)


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Page d'accueil de l'API."""
    return {
        "message": "Bienvenue sur l'API ProsArtisan IA Expert 🚀",
        "docs": "/docs",
        "health": "/health",
    }
