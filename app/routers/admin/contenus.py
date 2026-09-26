"""
Router Admin — Contenus RAG : upload et ingestion de documents, statistiques Qdrant, activation des documents et des métiers.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.session import async_session, get_db
from app.middleware.auth import require_permission
from app.models.document_config import DocumentConfig
from app.models.metier import Metier
from app.services.audit_service import audit_service
from app.services.document_service import DocumentVectorStoreError, document_service
from app.services.rag_service import rag_service
from ingestion.pipeline import run_ingestion

router = APIRouter()
logger = logging.getLogger(__name__)


MAX_ADMIN_UPLOAD_BYTES = 25 * 1024 * 1024


_SAFE_UPLOAD_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,150}$")
_ALLOWED_DOCUMENT_TYPES = {
    "fiche_technique",
    "guide_pratique",
    "guide_technique",
    "norme_officielle",
}
_ALLOWED_EXPERTISE_LEVELS = {"debutant", "intermediaire", "avance"}


def _write_upload_exclusive(file_path: str, content: bytes) -> None:
    """Écrit un upload sans jamais remplacer silencieusement un fichier."""
    with open(file_path, "xb") as destination:
        destination.write(content)


def _remove_upload(file_path: str, upload_dir: str) -> None:
    """Supprime le fichier temporaire puis son dossier de tâche s'il est vide."""
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
    try:
        os.rmdir(upload_dir)
    except (FileNotFoundError, OSError):
        pass


async def _run_admin_ingestion_task(
    *,
    job_id: uuid.UUID,
    actor_id: uuid.UUID,
    file_path: str,
    docs_dir: str,
    metier_id: int,
    secteur_id: int,
    type_document: str,
    niveau_expertise: str,
) -> None:
    """Exécute l'ingestion et trace son résultat avec une session dédiée."""
    action = "document.ingestion.completed"
    after: dict[str, Any]
    try:
        result = await run_ingestion(
            docs_dir=docs_dir,
            metier_id=metier_id,
            secteur_id=secteur_id,
            type_document=type_document,
            niveau_expertise=niveau_expertise,
        )
        errors = list(result.get("erreurs") or [])
        if errors:
            action = "document.ingestion.failed"
            after = {"status": "failed", "errors": errors}
            await asyncio.to_thread(_remove_upload, file_path, docs_dir)
        else:
            after = {
                "status": "completed",
                "processed_files": result.get("processed_files", 0),
                "ingested_chunks": result.get("ingested_chunks", 0),
            }
    except Exception as exc:
        logger.exception("Échec de l'ingestion admin %s", job_id)
        action = "document.ingestion.failed"
        after = {"status": "failed", "error": type(exc).__name__}
        await asyncio.to_thread(_remove_upload, file_path, docs_dir)

    try:
        async with async_session() as session:
            await audit_service.log_action(
                session,
                actor_id=actor_id,
                action=action,
                resource_type="document",
                resource_id=str(job_id),
                after=after,
            )
            await session.commit()
    except Exception:
        logger.exception("Échec de journalisation de l'ingestion admin %s", job_id)


@router.post("/upload-pdf", status_code=status.HTTP_202_ACCEPTED)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    metier_id: int = Form(..., gt=0),
    secteur_id: int = Form(..., gt=0),
    type_document: str = Form(...),
    niveau_expertise: str = Form(...),
    admin_id: uuid.UUID = Depends(require_permission("documents.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload un document PDF technique et lance son ingestion vectorielle en
    arrière-plan (sécurisé admin). L'ingestion (extraction, découpage,
    embeddings, indexation Qdrant) peut prendre du temps sur un gros document :
    elle ne bloque donc plus la requête HTTP. Consulter GET /api/admin/stats ou
    /api/admin/documents une fois le traitement terminé.
    """
    allowed_exts = (".pdf", ".md", ".markdown", ".txt")
    normalized_type = type_document.strip().lower()
    normalized_level = niveau_expertise.strip().lower().replace("é", "e")
    if normalized_type not in _ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Type de document non reconnu.",
        )
    if normalized_level not in _ALLOWED_EXPERTISE_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Niveau d'expertise non reconnu.",
        )

    metier_result = await db.execute(select(Metier).where(Metier.id == metier_id))
    if metier_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Métier introuvable.",
        )
    secteur_result = await db.execute(select(Metier).where(Metier.id == secteur_id))
    if secteur_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secteur introuvable.",
        )
    # Nom réduit à sa dernière composante et limité à un jeu de caractères sûr :
    # un nom comme "../../app/main.py" écrirait sinon hors du dossier d'upload.
    safe_name = os.path.basename((file.filename or "").replace("\\", "/"))
    if not _SAFE_UPLOAD_NAME_RE.match(safe_name) or not safe_name.lower().endswith(
        allowed_exts
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Nom de fichier invalide. Formats acceptés : PDF (.pdf), "
                "Markdown (.md), Texte (.txt) ; lettres, chiffres, espaces, "
                "points, tirets et soulignés uniquement."
            ),
        )

    job_id = uuid.uuid4()
    upload_dir = os.path.join(settings.upload_dir, "admin_docs", str(job_id))
    await asyncio.to_thread(os.makedirs, upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, safe_name)

    content = await file.read(MAX_ADMIN_UPLOAD_BYTES + 1)
    if len(content) > MAX_ADMIN_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Document trop volumineux (25 Mo maximum).",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier envoyé est vide.",
        )
    file_sha256 = hashlib.sha256(content).hexdigest()
    try:
        await asyncio.to_thread(_write_upload_exclusive, file_path, content)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un fichier portant ce nom existe déjà pour cette ingestion.",
        ) from exc

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="document.ingestion.requested",
        resource_type="document",
        resource_id=str(job_id),
        after={
            "filename": safe_name,
            "sha256": file_sha256,
            "size_bytes": len(content),
            "metier_id": metier_id,
            "secteur_id": secteur_id,
            "type_document": normalized_type,
            "niveau_expertise": normalized_level,
        },
        request=request,
    )
    try:
        await db.commit()
    except Exception:
        await asyncio.to_thread(_remove_upload, file_path, upload_dir)
        raise

    background_tasks.add_task(
        _run_admin_ingestion_task,
        job_id=job_id,
        actor_id=admin_id,
        file_path=file_path,
        docs_dir=upload_dir,
        metier_id=metier_id,
        secteur_id=secteur_id,
        type_document=normalized_type,
        niveau_expertise=normalized_level,
    )

    return {
        "message": f"Fichier {safe_name} reçu : ingestion vectorielle lancée en arrière-plan.",
        "file_path": file_path,
        "job_id": str(job_id),
        "sha256": file_sha256,
        "status": "processing",
    }


@router.get("/stats")
async def get_ingestion_stats(
    admin_id: uuid.UUID = Depends(require_permission("documents.write")),
) -> dict[str, Any]:
    """Retourne les statistiques réelles de la base de connaissances Qdrant."""
    try:
        from qdrant_client import AsyncQdrantClient

        qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        info = await qdrant_client.get_collection(
            collection_name=settings.qdrant_collection
        )
        total_chunks = info.points_count
    except Exception as exc:
        logger.exception("Statistiques Qdrant indisponibles.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base vectorielle momentanément indisponible.",
        ) from exc

    return {
        "collection": settings.qdrant_collection,
        "metiers_coverts": [],
        "total_chunks": total_chunks,
    }


@router.get("/documents")
async def get_documents_list(
    admin_id: uuid.UUID = Depends(require_permission("documents.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la liste des fiches et guides techniques ingérés dans Qdrant avec statut d'activation."""
    documents_map = {}
    stmt = select(DocumentConfig)
    res = await db.execute(stmt)
    doc_configs = {cfg.filename: cfg.is_active for cfg in res.scalars().all()}

    metiers_res = await db.execute(select(Metier))
    metier_names = {metier.id: metier.nom for metier in metiers_res.scalars().all()}

    try:
        from qdrant_client import AsyncQdrantClient

        qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

        # Récupérer les 1000 premiers points pour extraire les noms de fichiers uniques
        scroll_results = await qdrant_client.scroll(
            collection_name=settings.qdrant_collection,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        points = scroll_results[0]
        for p in points:
            payload = p.payload or {}
            doc_name = payload.get("document_name")
            if doc_name:
                metier_id = payload.get("metier_id", 1)

                if doc_name not in documents_map:
                    documents_map[doc_name] = {
                        "id": doc_name,  # Identifier par son nom de fichier
                        "filename": doc_name,
                        "metier": metier_names.get(metier_id, f"Métier {metier_id}"),
                        "metier_id": metier_id,
                        "chunks_count": 0,
                        "date_ingestion": datetime.now(UTC).strftime("%Y-%m-%d"),
                        "is_active": doc_configs.get(doc_name, True),
                    }
                documents_map[doc_name]["chunks_count"] += 1
    except Exception as exc:
        logger.exception("Liste documentaire Qdrant indisponible.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base vectorielle momentanément indisponible.",
        ) from exc

    return {"documents": list(documents_map.values())}


@router.patch("/documents/{doc_name}/toggle")
async def toggle_document_status(
    doc_name: str,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("documents.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Active ou désactive un document pour la consultation dans le chat RAG."""
    stmt = select(DocumentConfig).where(DocumentConfig.filename == doc_name)
    res = await db.execute(stmt)
    cfg = res.scalar_one_or_none()

    if cfg is None or not isinstance(cfg, DocumentConfig):
        new_status = False
        cfg = DocumentConfig(
            id=uuid.uuid4(),
            filename=doc_name,
            is_active=new_status,
        )
        db.add(cfg)
    else:
        new_status = not getattr(cfg, "is_active", True)
        cfg.is_active = new_status
        cfg.updated_at = func.now()

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="document.toggle",
        resource_type="document",
        resource_id=doc_name,
        after={"is_active": new_status},
        request=request,
    )
    await db.commit()
    await rag_service.invalidate_activation_cache()

    return {
        "status": "ok",
        "filename": doc_name,
        "is_active": new_status,
        "message": f"Document '{doc_name}' {'activé' if new_status else 'désactivé'} pour le chat.",
    }


@router.get("/metiers")
async def get_metiers_list(
    admin_id: uuid.UUID = Depends(require_permission("parametres.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la liste des métiers et leur statut d'activation pour le chat."""
    stmt = select(Metier).options(selectinload(Metier.sous_metiers)).order_by(Metier.id)
    res = await db.execute(stmt)
    metiers = res.scalars().all()
    return {
        "metiers": [
            {
                "id": m.id,
                "nom": m.nom,
                "slug": m.slug,
                "description": m.description,
                "is_active": getattr(m, "is_active", True),
                "sous_metiers_count": len(m.sous_metiers) if m.sous_metiers else 0,
            }
            for m in metiers
        ]
    }


@router.patch("/metiers/{metier_id}/toggle")
async def toggle_metier_status(
    metier_id: int,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Active ou désactive un pôle de métier complet pour les utilisateurs du chat."""
    stmt = select(Metier).where(Metier.id == metier_id)
    res = await db.execute(stmt)
    metier = res.scalar_one_or_none()
    if not metier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Métier introuvable."
        )

    new_status = not getattr(metier, "is_active", True)
    metier.is_active = new_status
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="metier.toggle",
        resource_type="metier",
        resource_id=str(metier_id),
        after={"is_active": new_status},
        request=request,
    )
    await db.commit()
    await rag_service.invalidate_activation_cache()

    return {
        "status": "ok",
        "metier_id": metier.id,
        "nom": metier.nom,
        "is_active": new_status,
        "message": f"Métier '{metier.nom}' {'activé' if new_status else 'désactivé'} pour le chat.",
    }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("documents.delete")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime un document après confirmation explicite de Qdrant."""
    config_result = await db.execute(
        select(DocumentConfig).where(DocumentConfig.filename == doc_id)
    )
    config = config_result.scalar_one_or_none()
    try:
        deletion = await document_service.delete_vectors(doc_id)
    except DocumentVectorStoreError as exc:
        logger.exception("Échec de suppression Qdrant du document %s", doc_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Suppression momentanément indisponible. Le document reste actif.",
        ) from exc

    if config is not None:
        await db.delete(config)
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="document.delete",
        resource_type="document",
        resource_id=doc_id,
        before={"config_present": config is not None},
        after={
            "status": "deleted",
            "qdrant_status": deletion.status,
            "qdrant_operation_id": deletion.operation_id,
        },
        request=request,
    )
    await db.commit()

    # Les réponses en cache pourraient encore citer le document supprimé.
    await rag_service.invalidate_activation_cache()

    return {
        "status": "success",
        "operation_id": deletion.operation_id,
        "message": f"Document {doc_id} supprimé de la base Qdrant.",
    }
