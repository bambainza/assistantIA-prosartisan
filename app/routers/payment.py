"""
Router Payment : paiements Mobile Money (Wave Checkout, Orange Money WebPay).

- `POST /init` : crée le paiement chez l'opérateur et renvoie son URL.
- `GET /transactions/{id}` : suivi par le client après retour de l'opérateur.
- `POST /webhooks/wave` (en-tête `Wave-Signature`) et
  `POST /webhooks/orange-money` (`notif_token`) : notifications officielles.
- `POST /webhook` : webhook générique signé `X-Signature` (agrégateur).
- `/demo/checkout/{session}` : page du simulateur d'opérateur (mode démo).
"""

from __future__ import annotations

import html
import logging
import re
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    Header,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session, get_db
from app.middleware.auth import get_current_user_id
from app.schemas.payment import (
    PaymentInitRequest,
    PaymentInitResponse,
    TransactionStatusResponse,
    WebhookPayload,
)
from app.services.cache_service import cache_service
from app.services.payment_providers.demo import (
    NotificationSimulee,
    charger_session,
    decision_du_payeur,
)
from app.services.payment_providers.wave import WAVE_SIGNATURE_HEADER
from app.services.payment_service import (
    TARIFS_PASS,
    PaiementIndisponibleError,
    WebhookNonAuthentifieError,
    payment_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment", tags=["Paiement Mobile Money"])

# Compteur "glissant" (30 jours) des webhooks rejetés pour signature invalide,
# exposé au dashboard sécurité admin (voir app.routers.admin.securite.get_security_stats).
_WEBHOOK_REJECTED_COUNTER_KEY = "prosartisan:security:webhook_rejected_total"
_SECURITY_COUNTER_TTL_SECONDS = 30 * 86400

_NOMS_OPERATEURS = {"WAVE": "Wave", "ORANGE": "Orange Money"}
_TELEPHONE_ORANGE_RE = re.compile(r"^(\+225)?07\d{8}$")
_CODE_OTP_RE = re.compile(r"^\d{4}$")


async def _rejeter_webhook(detail: str) -> HTTPException:
    await cache_service.increment(
        _WEBHOOK_REJECTED_COUNTER_KEY, _SECURITY_COUNTER_TTL_SECONDS
    )
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


@router.get("/tarifs")
async def get_tarifs() -> dict[str, Any]:
    """Retourne la grille tarifaire des Pass et Packs ProsArtisan."""
    return {
        "offres": TARIFS_PASS,
        "operateurs": list(_NOMS_OPERATEURS),
        "mode": "demo" if settings.payment_demo_mode else "live",
        "disponible": payment_service.paiement_disponible(),
    }


@router.post("/init", response_model=PaymentInitResponse)
async def init_payment(
    payload: PaymentInitRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> PaymentInitResponse:
    """Initialise un paiement Mobile Money pour débloquer un Pass ou Pack."""
    try:
        res = await payment_service.initialize_payment(
            db=db,
            user_id=current_user_id,
            type_pass=payload.type_pass,
            operateur=payload.operateur,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err
    except PaiementIndisponibleError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err)
        ) from err
    return PaymentInitResponse(**res)


@router.get("/transactions/{transaction_id}", response_model=TransactionStatusResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TransactionStatusResponse:
    """État d'une transaction de l'utilisateur (suivi après retour de l'opérateur)."""
    txn = await payment_service.get_transaction_status(
        db, current_user_id, transaction_id
    )
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction introuvable."
        )
    return TransactionStatusResponse(
        transaction_id=str(txn.id),
        statut=txn.statut_paiement,
        operateur=txn.operateur,
        montant=txn.montant,
        type_achat=txn.type_achat,
    )


# ── Webhooks officiels ──


@router.post("/webhooks/wave")
async def wave_webhook(
    request: Request,
    wave_signature: str | None = Header(None, alias=WAVE_SIGNATURE_HEADER),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Webhook Wave Checkout : `Wave-Signature` obligatoire (401 sinon)."""
    try:
        return await payment_service.handle_wave_webhook(
            db, await request.body(), wave_signature
        )
    except WebhookNonAuthentifieError as exc:
        raise await _rejeter_webhook(str(exc)) from exc


@router.post("/webhooks/orange-money")
async def orange_money_webhook(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Notification Orange Money WebPay : `notif_token` obligatoire (401 sinon)."""
    try:
        return await payment_service.handle_orange_money_notification(
            db, await request.body()
        )
    except WebhookNonAuthentifieError as exc:
        raise await _rejeter_webhook(str(exc)) from exc


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    payload: WebhookPayload,
    x_signature: str | None = Header(None, alias="X-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Webhook générique (agrégateur) avec signature HMAC SHA-256 `X-Signature`."""
    raw_body = await request.body()

    # La signature HMAC est obligatoire : un webhook non signé (ou mal signé)
    # est rejeté pour empêcher tout déblocage frauduleux de Pass premium.
    if not payment_service.verify_webhook_signature(raw_body, x_signature):
        raise await _rejeter_webhook("Signature HMAC manquante ou invalide")

    result = await payment_service.process_webhook(
        db=db,
        transaction_id=payload.transaction_id,
        statut=payload.status,
        montant=payload.montant,
    )

    if result.get("status") == "montant_invalide":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message"),
        )

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("message"),
        )

    return result


# ── Simulateur d'opérateur (mode démo) ──


def _demo_active() -> None:
    if not settings.payment_demo_mode or not payment_service.paiement_disponible():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


async def _livrer_notification(notification: NotificationSimulee) -> None:
    """Remet la notification simulée au traitement des webhooks réels (tâche de fond)."""
    try:
        async with async_session() as db:
            if notification.operateur == "WAVE":
                await payment_service.handle_wave_webhook(
                    db, notification.body, notification.headers[WAVE_SIGNATURE_HEADER]
                )
            else:
                await payment_service.handle_orange_money_notification(
                    db, notification.body
                )
    except Exception:
        logger.exception("Notification de paiement simulée non traitée.")


def _page(titre: str, corps: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titre)}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f4f5f7;margin:0;padding:16px;color:#1d2433}}
main{{max-width:420px;margin:24px auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 12px #0001}}
.bandeau{{background:#fff4d6;border:1px solid #f0c24b;border-radius:8px;padding:10px 12px;font-size:14px}}
.montant{{font-size:32px;font-weight:700;margin:16px 0 4px}}
label{{display:block;font-size:14px;margin-top:14px}}
input{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #c9ced8;border-radius:8px;font-size:16px}}
button{{width:100%;padding:12px;border:0;border-radius:8px;font-size:16px;margin-top:12px;cursor:pointer}}
.payer{{background:#1d6fe0;color:#fff}} .annuler{{background:#e8eaef;color:#1d2433}}
small{{color:#5b6475}}
</style></head><body><main>{corps}</main></body></html>"""
    )


@router.get("/demo/checkout/{session_id}", response_class=HTMLResponse)
async def demo_checkout_page(session_id: str) -> HTMLResponse:
    """Page de paiement simulée (équivalent de `wave_launch_url` / `payment_url`)."""
    _demo_active()
    state = await charger_session(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    operateur = _NOMS_OPERATEURS.get(state["operateur"], state["operateur"])
    action = html.escape(f"/api/payment/demo/checkout/{session_id}")
    if state["statut"] != "PENDING":
        return _page(
            "Paiement déjà traité",
            "<h1>Paiement déjà traité</h1><p>Vous pouvez revenir à ProsArtisan.</p>",
        )

    champs_orange = ""
    if state["operateur"] == "ORANGE":
        champs_orange = """
<label>Numéro Orange Money
<input name="telephone" inputmode="tel" required pattern="(\\+225)?07[0-9]{8}" placeholder="07 00 00 00 00"></label>
<label>Code de confirmation
<input name="code" inputmode="numeric" required pattern="[0-9]{4}" maxlength="4" placeholder="4 chiffres"></label>
<small>Démo : tout numéro 07XXXXXXXX et tout code à 4 chiffres sont acceptés.</small>"""

    return _page(
        f"Paiement {operateur} — simulation",
        f"""
<p class="bandeau">⚠️ <strong>Simulateur de paiement ProsArtisan</strong> — mode
démonstration. Aucun argent n'est débité ; ce parcours reproduit les étapes
{html.escape(operateur)} en attendant l'accès officiel.</p>
<p>Paiement {html.escape(operateur)} (simulé)</p>
<p class="montant">{int(state["montant"])} F CFA</p>
<small>Référence {html.escape(state["reference"])}</small>
<form method="post" action="{action}">
{champs_orange}
<button class="payer" name="decision" value="payer">Confirmer le paiement</button>
</form>
<form method="post" action="{action}">
<button class="annuler" name="decision" value="annuler" formnovalidate>Annuler</button>
</form>""",
    )


@router.post("/demo/checkout/{session_id}")
async def demo_checkout_decision(
    session_id: str,
    background_tasks: BackgroundTasks,
    decision: str = Form(...),
    telephone: str | None = Form(None),
    code: str | None = Form(None),
) -> RedirectResponse:
    """Décision du payeur : notification officielle simulée puis retour vers ProsArtisan."""
    _demo_active()
    state = await charger_session(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    accepte = decision == "payer"
    if (
        accepte
        and state["operateur"] == "ORANGE"
        and not (
            _TELEPHONE_ORANGE_RE.match((telephone or "").replace(" ", ""))
            and _CODE_OTP_RE.match(code or "")
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Numéro Orange Money ou code de confirmation invalide.",
        )

    notification = await decision_du_payeur(session_id, accepte)
    if notification is None:
        # Déjà traité (double clic) : retour simple vers l'application.
        return RedirectResponse(
            state["success_url"]
            if state["statut"] == "SUCCESS"
            else state["error_url"],
            status_code=status.HTTP_303_SEE_OTHER,
        )
    # Comme chez l'opérateur, la notification part indépendamment du retour
    # navigateur ; le client suit ensuite `GET /transactions/{id}`.
    background_tasks.add_task(_livrer_notification, notification)
    return RedirectResponse(
        notification.redirect_url, status_code=status.HTTP_303_SEE_OTHER
    )
