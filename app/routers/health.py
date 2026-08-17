"""Route de vérification de santé de l'application."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict:
    """Vérifie que le serveur est opérationnel."""
    return {
        "status": "ok",
        "service": "ProsArtisan IA Expert",
        "version": "0.1.0",
    }
