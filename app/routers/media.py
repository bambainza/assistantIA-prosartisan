"""
Router Médias : diffusion des photos de chantier via URL signée.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.services.media_service import media_service

router = APIRouter(prefix="/api/media", tags=["Médias"])

_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


@router.get("/chat-images/{name}")
async def get_chat_image(
    name: str,
    exp: int = Query(...),
    sig: str = Query(..., max_length=128),
) -> FileResponse:
    """Sert une photo de chantier si l'URL signée (délivrée au seul propriétaire) est valide."""
    path = media_service.resolve_signed(name, exp, sig)
    if path is None:
        # Même réponse pour signature invalide, expirée ou fichier absent :
        # aucune information sur l'existence d'une photo n'est divulguée.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Photo introuvable."
        )
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[path.suffix.lstrip(".")],
        headers={"Cache-Control": "private, max-age=3600"},
    )
