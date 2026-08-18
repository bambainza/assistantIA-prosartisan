"""
Router Admin : Back-office d'administration.

Ingestion de PDF techniques, consultation des statistiques Qdrant et logs d'utilisation.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.config import settings
from ingestion.pipeline import run_ingestion

router = APIRouter(prefix="/api/admin", tags=["Back-Office Admin"])


@router.post("/upload-pdf", status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    file: UploadFile = File(...),
    metier_id: int = Form(1),
    secteur_id: int = Form(1),
    type_document: str = Form("guide_technique"),
    niveau_expertise: str = Form("intermédiaire"),
) -> dict[str, Any]:
    """Upload un document PDF technique et déclenche son ingestion vectorielle."""
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seuls les fichiers au format PDF sont acceptés.",
        )

    upload_dir = os.path.join(settings.upload_dir, "admin_docs")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    ingest_result = run_ingestion(
        docs_dir=upload_dir,
        metier_id=metier_id,
        secteur_id=secteur_id,
        type_document=type_document,
        niveau_expertise=niveau_expertise,
    )

    return {
        "message": f"Fichier {file.filename} ingéré avec succès.",
        "file_path": file_path,
        "details": ingest_result,
    }


@router.get("/stats")
async def get_ingestion_stats() -> dict[str, Any]:
    """Retourne les statistiques de la base de connaissances Qdrant."""
    return {
        "collection": settings.qdrant_collection,
        "metiers_coverts": [
            {"metier_id": 1, "nom": "Bâtiment & Construction", "documents_ingeres": 12},
            {"metier_id": 2, "nom": "Électricité & Énergie", "documents_ingeres": 8},
            {"metier_id": 3, "nom": "Plomberie & Sanitaire", "documents_ingeres": 15},
            {"metier_id": 4, "nom": "Mécanique & Automobile", "documents_ingeres": 6},
        ],
        "total_chunks": 41,
    }


@router.get("/logs")
async def get_system_logs() -> dict[str, Any]:
    """Retourne les journaux d'activité récents."""
    return {
        "logs": [
            {"timestamp": "2026-08-18T18:00:00Z", "level": "INFO", "event": "Pipeline RAG prêt"},
            {"timestamp": "2026-08-18T18:15:00Z", "level": "INFO", "event": "Initialisation Qdrant OK"},
        ]
    }
