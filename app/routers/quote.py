"""Router FastAPI pour la gestion des devis et factures pro-forma."""

from __future__ import annotations

import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_current_user_id
from app.models.quote import Quote
from app.models.user import User
from app.schemas.quote import (
    QuoteCreate,
    QuoteExtractRequest,
    QuoteExtractResponse,
    QuoteResponse,
    QuoteStatusUpdate,
    QuoteUpdate,
)
from app.services.quote_service import quote_service

router = APIRouter(prefix="/api/quotes", tags=["Devis & Facturation Artisan"])


def _to_quote_response(quote: Quote, artisan: User | None = None) -> QuoteResponse:
    artisan_nom = (
        artisan.nom
        if artisan and hasattr(artisan, "nom") and artisan.nom
        else "Artisan ProsArtisan"
    )
    artisan_tel = (
        artisan.telephone
        if artisan and hasattr(artisan, "telephone") and artisan.telephone
        else ""
    )

    wa_text = quote_service.generate_whatsapp_text(
        quote=quote,
        artisan_nom=artisan_nom,
        artisan_phone=artisan_tel,
    )
    encoded_text = urllib.parse.quote(wa_text)
    clean_phone = (
        (quote.client_telephone or "")
        .replace(" ", "")
        .replace("+", "")
        .replace("-", "")
    )
    wa_url = (
        f"https://wa.me/{clean_phone}?text={encoded_text}"
        if clean_phone
        else f"https://wa.me/?text={encoded_text}"
    )

    return QuoteResponse(
        id=quote.id,
        user_id=quote.user_id,
        numero=quote.numero,
        titre=quote.titre,
        client_nom=quote.client_nom,
        client_telephone=quote.client_telephone,
        client_adresse=quote.client_adresse,
        metier_id=quote.metier_id,
        statut=quote.statut,
        items=quote.items,
        total_ht=quote.total_ht,
        remise_pct=quote.remise_pct,
        tva_pct=quote.tva_pct,
        total_ttc=quote.total_ttc,
        acompte_demande_pct=quote.acompte_demande_pct,
        montant_acompte=quote.montant_acompte,
        solde_restant=quote.total_ttc - quote.montant_acompte,
        mode_paiement=quote.mode_paiement,
        delai_jours=quote.delai_jours,
        notes=quote.notes,
        date_emission=quote.date_emission,
        date_validite=quote.date_validite,
        whatsapp_share_text=wa_text,
        whatsapp_share_url=wa_url,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


@router.post(
    "/extract",
    response_model=QuoteExtractResponse,
    summary="Extraire les lignes de devis par IA depuis une note vocale ou écrite",
)
async def extract_quote_endpoint(
    payload: QuoteExtractRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> QuoteExtractResponse:
    """Analyse une formulation vocale ou un texte d'artisan et génère les postes chiffrés."""
    return await quote_service.extract_quote_from_text(
        description_brute=payload.description_brute,
        client_nom=payload.client_nom,
        client_telephone=payload.client_telephone,
        metier_id=payload.metier_id,
    )


@router.post(
    "",
    response_model=QuoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un nouveau devis",
)
async def create_quote_endpoint(
    payload: QuoteCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Enregistre un devis calculé pour l'artisan connecté."""
    totals = quote_service.calculate_totals(
        items=payload.items,
        remise_pct=payload.remise_pct,
        tva_pct=payload.tva_pct,
        acompte_pct=payload.acompte_demande_pct,
    )

    numero = await quote_service.generate_next_number(db)
    now = datetime.now(UTC).replace(tzinfo=None)
    validite = now + timedelta(days=30)

    quote = Quote(
        id=uuid.uuid4(),
        user_id=user_id,
        numero=numero,
        titre=payload.titre,
        client_nom=payload.client_nom,
        client_telephone=payload.client_telephone,
        client_adresse=payload.client_adresse,
        metier_id=payload.metier_id,
        statut="BROUILLON",
        items=totals["items"],
        total_ht=totals["total_ht"],
        remise_pct=totals["remise_pct"],
        tva_pct=totals["tva_pct"],
        total_ttc=totals["total_ttc"],
        acompte_demande_pct=totals["acompte_pct"],
        montant_acompte=totals["montant_acompte"],
        mode_paiement=payload.mode_paiement,
        delai_jours=payload.delai_jours,
        notes=payload.notes,
        date_emission=now,
        date_validite=validite,
        created_at=now,
        updated_at=now,
    )

    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    # Récupérer l'utilisateur pour le contact WhatsApp
    artisan_res = await db.execute(select(User).where(User.id == user_id))
    artisan = artisan_res.scalar_one_or_none()

    return _to_quote_response(quote, artisan)


@router.get(
    "",
    response_model=list[QuoteResponse],
    summary="Lister les devis de l'artisan connecté",
)
async def list_quotes_endpoint(
    statut: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[QuoteResponse]:
    """Retourne la liste des devis de l'artisan (isolés par propriétaire, anti-IDOR)."""
    stmt = select(Quote).where(Quote.user_id == user_id)

    if statut:
        stmt = stmt.where(Quote.statut == statut.upper())
    if q:
        search_filter = f"%{q.strip()}%"
        stmt = stmt.where(
            (Quote.titre.ilike(search_filter))
            | (Quote.client_nom.ilike(search_filter))
            | (Quote.numero.ilike(search_filter))
        )

    stmt = stmt.order_by(Quote.created_at.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    quotes = res.scalars().all()

    artisan_res = await db.execute(select(User).where(User.id == user_id))
    artisan = artisan_res.scalar_one_or_none()

    return [_to_quote_response(q_obj, artisan) for q_obj in quotes]


@router.get(
    "/{quote_id}",
    response_model=QuoteResponse,
    summary="Obtenir le détail d'un devis",
)
async def get_quote_endpoint(
    quote_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Récupère un devis par son identifiant avec vérification de propriété."""
    stmt = select(Quote).where(Quote.id == quote_id, Quote.user_id == user_id)
    res = await db.execute(stmt)
    quote = res.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Devis introuvable ou accès non autorisé.",
        )

    artisan_res = await db.execute(select(User).where(User.id == user_id))
    artisan = artisan_res.scalar_one_or_none()

    return _to_quote_response(quote, artisan)


@router.put(
    "/{quote_id}",
    response_model=QuoteResponse,
    summary="Mettre à jour un devis",
)
async def update_quote_endpoint(
    quote_id: uuid.UUID,
    payload: QuoteUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Modifie le devis et recalcule les totaux."""
    stmt = select(Quote).where(Quote.id == quote_id, Quote.user_id == user_id)
    res = await db.execute(stmt)
    quote = res.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Devis introuvable ou accès non autorisé.",
        )

    if payload.titre is not None:
        quote.titre = payload.titre
    if payload.client_nom is not None:
        quote.client_nom = payload.client_nom
    if payload.client_telephone is not None:
        quote.client_telephone = payload.client_telephone
    if payload.client_adresse is not None:
        quote.client_adresse = payload.client_adresse
    if payload.mode_paiement is not None:
        quote.mode_paiement = payload.mode_paiement
    if payload.delai_jours is not None:
        quote.delai_jours = payload.delai_jours
    if payload.notes is not None:
        quote.notes = payload.notes

    # Recalcul si items ou remises changent
    items_to_use = payload.items if payload.items is not None else quote.items
    remise_to_use = (
        payload.remise_pct if payload.remise_pct is not None else quote.remise_pct
    )
    tva_to_use = payload.tva_pct if payload.tva_pct is not None else quote.tva_pct
    acompte_to_use = (
        payload.acompte_demande_pct
        if payload.acompte_demande_pct is not None
        else quote.acompte_demande_pct
    )

    totals = quote_service.calculate_totals(
        items=items_to_use,
        remise_pct=remise_to_use,
        tva_pct=tva_to_use,
        acompte_pct=acompte_to_use,
    )

    quote.items = totals["items"]
    quote.total_ht = totals["total_ht"]
    quote.remise_pct = totals["remise_pct"]
    quote.tva_pct = totals["tva_pct"]
    quote.total_ttc = totals["total_ttc"]
    quote.acompte_demande_pct = totals["acompte_pct"]
    quote.montant_acompte = totals["montant_acompte"]
    quote.updated_at = datetime.now(UTC).replace(tzinfo=None)

    await db.commit()
    await db.refresh(quote)

    artisan_res = await db.execute(select(User).where(User.id == user_id))
    artisan = artisan_res.scalar_one_or_none()

    return _to_quote_response(quote, artisan)


@router.patch(
    "/{quote_id}/status",
    response_model=QuoteResponse,
    summary="Changer le statut d'un devis",
)
async def update_quote_status_endpoint(
    quote_id: uuid.UUID,
    payload: QuoteStatusUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Passe le devis en ENVOYE, ACCEPTE, REFUSE ou FACTURE."""
    stmt = select(Quote).where(Quote.id == quote_id, Quote.user_id == user_id)
    res = await db.execute(stmt)
    quote = res.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Devis introuvable ou accès non autorisé.",
        )

    quote.statut = payload.statut.upper()
    quote.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(quote)

    artisan_res = await db.execute(select(User).where(User.id == user_id))
    artisan = artisan_res.scalar_one_or_none()

    return _to_quote_response(quote, artisan)


@router.delete(
    "/{quote_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un devis",
)
async def delete_quote_endpoint(
    quote_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Supprime un devis de l'artisan."""
    stmt = select(Quote).where(Quote.id == quote_id, Quote.user_id == user_id)
    res = await db.execute(stmt)
    quote = res.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Devis introuvable ou accès non autorisé.",
        )

    await db.delete(quote)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{quote_id}/html",
    response_class=HTMLResponse,
    summary="Générer la vue HTML imprimable du devis",
)
async def render_quote_html_endpoint(
    quote_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Retourne la page HTML complète du devis pour impression / PDF."""
    stmt = select(Quote).where(Quote.id == quote_id, Quote.user_id == user_id)
    res = await db.execute(stmt)
    quote = res.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Devis introuvable ou accès non autorisé.",
        )

    artisan_res = await db.execute(select(User).where(User.id == user_id))
    artisan = artisan_res.scalar_one_or_none()

    html_content = quote_service.generate_quote_html(quote, artisan)
    return HTMLResponse(content=html_content)
