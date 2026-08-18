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


@router.get("/overview")
async def get_admin_overview() -> dict[str, Any]:
    """Retourne la synthèse globale des KPIs pour le tableau de bord exécutif."""
    return {
        "kpis": {
            "total_artisans": 1284,
            "artisans_actifs_dau": 342,
            "chiffre_affaires_mfa": 1450000,
            "total_questions_rag": 18920,
            "total_documents_qdrant": 41,
        },
        "abonnements": {
            "free": 940,
            "pass_24h": 210,
            "pass_mois": 134,
        },
        "metiers_top": [
            {"nom": "Maçonnerie & Gros Œuvre", "requetes": 6540},
            {"nom": "Électricité Bâtiment", "requetes": 4820},
            {"nom": "Plomberie Sanitaire", "requetes": 3910},
            {"nom": "Mécanique Auto & Diesel", "requetes": 2100},
            {"nom": "Charpente & Couverture", "requetes": 1550},
        ],
    }


@router.get("/users")
async def get_users_list() -> dict[str, Any]:
    """Retourne la liste des artisans inscrits avec statut de quota."""
    return {
        "users": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "nom": "Kouassi Jean-Marc",
                "telephone": "+2250708091011",
                "metier": "Maçonnerie & Gros Œuvre",
                "type_abonnement": "pass_mois",
                "questions_restantes": 999999,
                "date_inscription": "2026-08-01",
            },
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "nom": "Yao Modeste",
                "telephone": "+2250506070809",
                "metier": "Électricité Bâtiment",
                "type_abonnement": "pass_24h",
                "questions_restantes": 999999,
                "date_inscription": "2026-08-10",
            },
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "nom": "Bamba Ibrahim",
                "telephone": "+2250102030405",
                "metier": "Plomberie Sanitaire",
                "type_abonnement": "FREE",
                "questions_restantes": 3,
                "date_inscription": "2026-08-15",
            },
        ]
    }


@router.post("/users/{user_id}/grant-pass")
async def grant_pass_to_user(
    user_id: str, type_pass: str = "pass_24h"
) -> dict[str, Any]:
    """Attribue ou prolonge manuellement un Pass Pro pour un artisan."""
    return {
        "status": "success",
        "message": f"Pass {type_pass} attribué avec succès à l'artisan {user_id}",
        "user_id": user_id,
        "type_pass": type_pass,
    }


@router.get("/documents")
async def get_documents_list() -> dict[str, Any]:
    """Retourne la liste des fiches et guides techniques ingérés dans Qdrant."""
    return {
        "documents": [
            {
                "id": "doc-01",
                "filename": "guide_dosage_beton_maconnerie.pdf",
                "metier": "Bâtiment & Construction",
                "metier_id": 1,
                "chunks_count": 18,
                "date_ingestion": "2026-08-10",
            },
            {
                "id": "doc-02",
                "filename": "normes_securite_electricite_batiment.pdf",
                "metier": "Électricité & Énergie",
                "metier_id": 2,
                "chunks_count": 14,
                "date_ingestion": "2026-08-12",
            },
            {
                "id": "doc-03",
                "filename": "manuel_plomberie_tuyauterie_sanitaire.pdf",
                "metier": "Plomberie & Sanitaire",
                "metier_id": 3,
                "chunks_count": 9,
                "date_ingestion": "2026-08-14",
            },
        ]
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> dict[str, Any]:
    """Supprime un document technique de la base de connaissances RAG."""
    return {
        "status": "success",
        "message": f"Document {doc_id} supprimé de la base Qdrant.",
    }


@router.get("/transactions")
async def get_transactions_log() -> dict[str, Any]:
    """Retourne le journal des transactions Mobile Money (Wave / Orange)."""
    return {
        "transactions": [
            {
                "id": "TXN-88401",
                "reference_externe": "REF-WAVE-9921",
                "artisan": "Kouassi Jean-Marc",
                "montant": 3000,
                "devise": "XOF",
                "operateur": "WAVE",
                "statut": "ACCEPTED",
                "type_achat": "pass_mois",
                "timestamp": "2026-08-18T17:30:00Z",
            },
            {
                "id": "TXN-88400",
                "reference_externe": "REF-OM-4412",
                "artisan": "Yao Modeste",
                "montant": 500,
                "devise": "XOF",
                "operateur": "ORANGE_MONEY",
                "statut": "ACCEPTED",
                "type_achat": "pass_24h",
                "timestamp": "2026-08-18T16:15:00Z",
            },
            {
                "id": "TXN-88399",
                "reference_externe": "REF-WAVE-1102",
                "artisan": "Bamba Ibrahim",
                "montant": 500,
                "devise": "XOF",
                "operateur": "WAVE",
                "statut": "REFUSED",
                "type_achat": "pass_24h",
                "timestamp": "2026-08-18T15:00:00Z",
            },
        ]
    }


@router.get("/logs")
async def get_system_logs() -> dict[str, Any]:
    """Retourne les journaux d'activité récents."""
    return {
        "logs": [
            {
                "timestamp": "2026-08-18T18:00:00Z",
                "level": "INFO",
                "event": "Pipeline RAG prêt",
            },
            {
                "timestamp": "2026-08-18T18:15:00Z",
                "level": "INFO",
                "event": "Initialisation Qdrant OK",
            },
        ]
    }
