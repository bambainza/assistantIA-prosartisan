"""Router Paramètres : gestion des données de référence qui alimentent les
listes de choix du back-office et de l'ingestion RAG (métiers, sous-métiers,
catégories d'actualités).

Toutes les routes exigent la permission RBAC `parametres.read` (lecture) ou
`parametres.write` (création/modification/désactivation/suppression) — voir
AGENTS.md §11. Ces permissions sont indépendantes de celles des modules qui
consomment ces listes (ex: `actualites.write`) : un admin peut créer des
actualités sans pouvoir modifier la liste des catégories, et inversement.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_permission
from app.schemas.parametres import (
    ActualiteCategorieCreateRequest,
    ActualiteCategorieOut,
    ActualiteCategorieUpdateRequest,
    MetierCreateRequest,
    MetierOut,
    MetierUpdateRequest,
    SousMetierCreateRequest,
    SousMetierOut,
    SousMetierUpdateRequest,
)
from app.services.audit_service import audit_service
from app.services.parametres_service import parametres_service

router = APIRouter(prefix="/api/admin/parametres", tags=["Paramètres (Back-office)"])


async def _commit_or_409(
    db: AsyncSession, *, detail: str = "Un slug ou un code identique existe déjà."
) -> None:
    """Valide la transaction en cours, ou la annule et lève un 409 propre.

    Toute contrainte d'intégrité (slug/code dupliqué, ligne encore référencée
    par une clé étrangère) ne se manifeste qu'au COMMIT avec SQLAlchemy async
    (pas avant) : c'est donc le seul point où l'intercepter pour la traduire
    en réponse HTTP exploitable plutôt qu'en 500 générique.
    """
    try:
        await db.commit()
    except IntegrityError as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=detail
        ) from err


# ── Métiers ──────────────────────────────────────────────────────────────
@router.get("/metiers", response_model=list[MetierOut])
async def list_metiers(
    admin_id: uuid.UUID = Depends(require_permission("parametres.read")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Liste complète des métiers (actifs et désactivés) avec leurs sous-métiers."""
    return await parametres_service.list_metiers(db)


@router.post("/metiers", status_code=status.HTTP_201_CREATED, response_model=MetierOut)
async def create_metier(
    payload: MetierCreateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Crée un nouveau métier de référence."""
    metier = await parametres_service.create_metier(
        db, nom=payload.nom, slug=payload.slug, description=payload.description
    )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.metier.create",
        resource_type="metier",
        resource_id=None,
        after={"nom": payload.nom, "slug": payload.slug},
        request=request,
    )
    await _commit_or_409(db, detail="Un métier avec ce slug existe déjà.")
    await db.refresh(metier)
    return metier


@router.put("/metiers/{metier_id}", response_model=MetierOut)
async def update_metier(
    metier_id: int,
    payload: MetierUpdateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Met à jour le nom, le slug ou la description d'un métier."""
    metier = await parametres_service.update_metier(
        db,
        metier_id,
        nom=payload.nom,
        slug=payload.slug,
        description=payload.description,
    )
    if metier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Métier introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.metier.update",
        resource_type="metier",
        resource_id=str(metier_id),
        after=payload.model_dump(exclude_unset=True),
        request=request,
    )
    await _commit_or_409(db, detail="Un métier avec ce slug existe déjà.")
    await db.refresh(metier)
    return metier


@router.patch("/metiers/{metier_id}/toggle", response_model=MetierOut)
async def toggle_metier(
    metier_id: int,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Active ou désactive un métier (ne le supprime pas)."""
    metier = await parametres_service.toggle_metier(db, metier_id)
    if metier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Métier introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.metier.toggle",
        resource_type="metier",
        resource_id=str(metier_id),
        after={"is_active": metier.is_active},
        request=request,
    )
    await db.commit()
    await db.refresh(metier)
    return metier


@router.delete("/metiers/{metier_id}")
async def delete_metier(
    metier_id: int,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime définitivement un métier.

    Refusé (409) s'il est encore référencé par des artisans ou des actualités
    — désactivez-le plutôt via `/toggle` dans ce cas.
    """
    deleted = await parametres_service.delete_metier(db, metier_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Métier introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.metier.delete",
        resource_type="metier",
        resource_id=str(metier_id),
        after=None,
        request=request,
    )
    await _commit_or_409(
        db,
        detail=(
            "Ce métier est encore utilisé (artisans, actualités...) : "
            "désactivez-le plutôt que de le supprimer."
        ),
    )
    return {"status": "success", "message": "Métier supprimé."}


# ── Sous-métiers ─────────────────────────────────────────────────────────
@router.post(
    "/sous-metiers", status_code=status.HTTP_201_CREATED, response_model=SousMetierOut
)
async def create_sous_metier(
    payload: SousMetierCreateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Crée une spécialité rattachée à un métier existant."""
    sous_metier = await parametres_service.create_sous_metier(
        db, metier_id=payload.metier_id, nom=payload.nom, slug=payload.slug
    )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.sous_metier.create",
        resource_type="sous_metier",
        resource_id=None,
        after={"metier_id": payload.metier_id, "nom": payload.nom},
        request=request,
    )
    await _commit_or_409(db, detail="Slug déjà utilisé ou métier parent introuvable.")
    await db.refresh(sous_metier)
    return sous_metier


@router.put("/sous-metiers/{sous_metier_id}", response_model=SousMetierOut)
async def update_sous_metier(
    sous_metier_id: int,
    payload: SousMetierUpdateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Met à jour le nom ou le slug d'une spécialité."""
    sous_metier = await parametres_service.update_sous_metier(
        db, sous_metier_id, nom=payload.nom, slug=payload.slug
    )
    if sous_metier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sous-métier introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.sous_metier.update",
        resource_type="sous_metier",
        resource_id=str(sous_metier_id),
        after=payload.model_dump(exclude_unset=True),
        request=request,
    )
    await _commit_or_409(db, detail="Slug déjà utilisé.")
    await db.refresh(sous_metier)
    return sous_metier


@router.delete("/sous-metiers/{sous_metier_id}")
async def delete_sous_metier(
    sous_metier_id: int,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime une spécialité. Refusé (409) si des artisans la référencent encore."""
    deleted = await parametres_service.delete_sous_metier(db, sous_metier_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sous-métier introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.sous_metier.delete",
        resource_type="sous_metier",
        resource_id=str(sous_metier_id),
        after=None,
        request=request,
    )
    await _commit_or_409(
        db, detail="Ce sous-métier est encore utilisé par des artisans."
    )
    return {"status": "success", "message": "Sous-métier supprimé."}


# ── Catégories d'actualités ──────────────────────────────────────────────
@router.get("/actualite-categories", response_model=list[ActualiteCategorieOut])
async def list_categories(
    admin_id: uuid.UUID = Depends(require_permission("parametres.read")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Liste complète des catégories d'actualité (actives et désactivées)."""
    return await parametres_service.list_categories(db)


@router.post(
    "/actualite-categories",
    status_code=status.HTTP_201_CREATED,
    response_model=ActualiteCategorieOut,
)
async def create_categorie(
    payload: ActualiteCategorieCreateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Crée une nouvelle catégorie d'actualité."""
    categorie = await parametres_service.create_categorie(
        db, code=payload.code, label=payload.label
    )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.categorie.create",
        resource_type="actualite_categorie",
        resource_id=None,
        after={"code": payload.code, "label": payload.label},
        request=request,
    )
    await _commit_or_409(db, detail="Une catégorie avec ce code existe déjà.")
    await db.refresh(categorie)
    return categorie


@router.put(
    "/actualite-categories/{categorie_id}", response_model=ActualiteCategorieOut
)
async def update_categorie(
    categorie_id: int,
    payload: ActualiteCategorieUpdateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Renomme le libellé d'une catégorie (le code reste immuable)."""
    categorie = await parametres_service.update_categorie(
        db, categorie_id, label=payload.label
    )
    if categorie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Catégorie introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.categorie.update",
        resource_type="actualite_categorie",
        resource_id=str(categorie_id),
        after={"label": payload.label},
        request=request,
    )
    await db.commit()
    await db.refresh(categorie)
    return categorie


@router.patch(
    "/actualite-categories/{categorie_id}/toggle",
    response_model=ActualiteCategorieOut,
)
async def toggle_categorie(
    categorie_id: int,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Active ou désactive une catégorie (les actualités déjà créées ne sont pas affectées)."""
    categorie = await parametres_service.toggle_categorie(db, categorie_id)
    if categorie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Catégorie introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.categorie.toggle",
        resource_type="actualite_categorie",
        resource_id=str(categorie_id),
        after={"is_active": categorie.is_active},
        request=request,
    )
    await db.commit()
    await db.refresh(categorie)
    return categorie


@router.delete("/actualite-categories/{categorie_id}")
async def delete_categorie(
    categorie_id: int,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("parametres.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime définitivement une catégorie (préférez la désactiver si elle a
    déjà été utilisée sur des actualités existantes)."""
    deleted = await parametres_service.delete_categorie(db, categorie_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Catégorie introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="parametres.categorie.delete",
        resource_type="actualite_categorie",
        resource_id=str(categorie_id),
        after=None,
        request=request,
    )
    await db.commit()
    return {"status": "success", "message": "Catégorie supprimée."}
