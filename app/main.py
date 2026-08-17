"""
ProsArtisan IA Expert — Point d'entrée FastAPI.

Assistant IA conversationnel pour artisans professionnels.
Architecture RAG + Freemium + Mobile Money.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.init_db import init_db
from app.routers import health


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
# Les routers suivants seront ajoutés en Phase 2+ :
# app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
# app.include_router(chat.router, prefix="/api", tags=["Chat IA"])
# app.include_router(payment.router, prefix="/api/payment", tags=["Paiement"])
# app.include_router(quota.router, prefix="/api/quota", tags=["Quotas"])


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Page d'accueil de l'API."""
    return {
        "message": "Bienvenue sur l'API ProsArtisan IA Expert 🚀",
        "docs": "/docs",
        "health": "/health",
    }
