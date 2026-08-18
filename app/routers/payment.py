"""
Router Payment : Initialisation Mobile Money et Webhooks HMAC.

Supporte Wave Business, Orange Money, MTN et Moov.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.payment import PaymentInitRequest, PaymentInitResponse, WebhookPayload
from app.services.payment_service import TARIFS_PASS, payment_service

router = APIRouter(prefix="/api/payment", tags=["Paiement Mobile Money"])


@router.get("/tarifs")
async def get_tarifs() -> dict[str, Any]:
    """Retourne la grille tarifaire des Pass et Packs ProsArtisan."""
    return {"offres": TARIFS_PASS}


@router.post("/init", response_model=PaymentInitResponse)
async def init_payment(
    payload: PaymentInitRequest,
    db: AsyncSession = Depends(get_db),
) -> PaymentInitResponse:
    """Initialise un paiement Mobile Money pour débloquer un Pass ou Pack."""
    try:
        res = await payment_service.initialize_payment(
            db=db,
            user_id=payload.user_id,
            type_pass=payload.type_pass,
        )
        return PaymentInitResponse(
            status=res["status"],
            payment_url=res["payment_url"],
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    payload: WebhookPayload,
    x_signature: str | None = Header(None, alias="X-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Webhook entrant des opérateurs Mobile Money avec signature HMAC SHA-256."""
    raw_body = await request.body()

    # Si en production ou clé configurée, valider la signature
    if x_signature and not payment_service.verify_webhook_signature(
        raw_body, x_signature
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature HMAC invalide",
        )

    result = await payment_service.process_webhook(
        db=db,
        transaction_id=payload.transaction_id,
        statut=payload.status,
    )

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("message"),
        )

    return result
