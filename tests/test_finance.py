"""Tests pour le module Finance (back-office admin) : KPIs, journal filtrable,
remboursement et correction manuelle de statut sur les transactions Mobile
Money.

Régression sécurité : sans `require_permission`, un admin restreint pourrait
consulter le chiffre d'affaires réel ou rembourser une transaction sans
détenir `transactions.read`/`finance.write` — ces tests échoueraient sans le
garde-fou de app.middleware.auth.require_permission.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.role import Permission, Role
from app.models.transaction import TransactionMobileMoney
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def legacy_admin_user():
    """Admin historique (is_admin=True) sans rôle RBAC : accès complet hérité."""
    return User(
        id=uuid.uuid4(),
        email="legacy_admin_finance@prosartisan.ci",
        nom="Admin Historique",
        is_admin=True,
        role_id=None,
    )


@pytest.fixture
def restricted_admin_user():
    """Admin avec un rôle RBAC ne donnant accès à rien du module Finance."""
    role = Role(id=uuid.uuid4(), code="autre_role", label="Autre rôle")
    role.permissions = [Permission(id=uuid.uuid4(), code="actualites.read")]
    user = User(
        id=uuid.uuid4(),
        email="restricted_finance@prosartisan.ci",
        nom="Admin Restreint",
        is_admin=True,
    )
    user.role = role
    return user


def _sequenced_db(responses):
    """Mock DB : chaque appel `db.execute` consomme la réponse suivante.

    `responses` est une liste de tuples `("scalar", valeur)` ou `("rows", [..])`
    (pour un `.all()` générique, utilisé aussi bien pour des lignes de
    transaction que pour un `scalar()` de comptage via une valeur brute).
    """

    async def custom_mock_db():
        session = MagicMock()
        queue = list(responses)

        async def mock_execute(stmt):
            kind, value = queue.pop(0)
            mock_res = MagicMock()
            if kind == "scalar":
                mock_res.scalar_one_or_none.return_value = value
                mock_res.scalar.return_value = value
            else:
                mock_res.all.return_value = value
                mock_res.scalars.return_value.all.return_value = value
            return mock_res

        session.execute = mock_execute
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    return custom_mock_db


@pytest.mark.asyncio
async def test_finance_overview_success(legacy_admin_user):
    """Un admin avec accès complet peut consulter les KPIs financiers."""
    now = datetime.now(UTC).replace(tzinfo=None)
    txn_rows = [
        (3000, "ACCEPTED", "WAVE", now),
        (1500, "ACCEPTED", "ORANGE", now),
        (500, "PENDING", "WAVE", now),
        (3000, "REFUNDED", "WAVE", now),
    ]
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),  # require_permission
            ("rows", txn_rows),  # get_overview
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/finance/overview",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["revenu_total"] == 4500
        assert body["revenu_rembourse_total"] == 3000
        assert body["total_transactions"] == 4
        assert body["par_operateur"] == {"WAVE": 3000, "ORANGE": 1500}
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_finance_overview_bloque_sans_permission(restricted_admin_user):
    """Un admin sans 'transactions.read' ne peut pas consulter les KPIs financiers."""
    app.dependency_overrides[get_db] = _sequenced_db(
        [("scalar", restricted_admin_user)]
    )
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/finance/overview",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_refund_transaction_success(legacy_admin_user):
    """Un admin avec 'finance.write' peut rembourser une transaction aboutie."""
    txn = TransactionMobileMoney(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        montant=3000,
        devise="XOF",
        operateur="WAVE",
        statut_paiement="ACCEPTED",
        type_achat="pass_mois",
    )
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),  # require_permission
            ("scalar", txn),  # transaction ciblée
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/finance/transactions/{txn.id}/refund",
                headers={"Authorization": f"Bearer {token}"},
                json={"reason": "Litige artisan confirmé"},
            )
        assert res.status_code == 200
        assert txn.statut_paiement == "REFUNDED"
        assert txn.refund_reason == "Litige artisan confirmé"
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_refund_transaction_statut_non_remboursable(legacy_admin_user):
    """Rembourser une transaction jamais aboutie (PENDING) doit échouer avec 400."""
    txn = TransactionMobileMoney(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        montant=500,
        devise="XOF",
        operateur="WAVE",
        statut_paiement="PENDING",
        type_achat="pass_24h",
    )
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),
            ("scalar", txn),
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/finance/transactions/{txn.id}/refund",
                headers={"Authorization": f"Bearer {token}"},
                json={"reason": "Test"},
            )
        assert res.status_code == 400
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_refund_bloque_sans_permission(restricted_admin_user):
    """Un admin sans 'finance.write' ne peut pas rembourser de transaction."""
    app.dependency_overrides[get_db] = _sequenced_db(
        [("scalar", restricted_admin_user)]
    )
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/finance/transactions/{uuid.uuid4()}/refund",
                headers={"Authorization": f"Bearer {token}"},
                json={"reason": "Test"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_adjust_status_rejette_statut_non_autorise(legacy_admin_user):
    """Tenter de forcer le statut 'REFUNDED' via l'ajustement manuel doit échouer.

    Le remboursement a sa propre voie dédiée (`/refund`, qui trace le motif
    et l'acteur) : l'endpoint générique de correction de statut la refuse
    explicitement pour garder une seule source de vérité.
    """
    app.dependency_overrides[get_db] = _sequenced_db(
        [("scalar", legacy_admin_user)]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/finance/transactions/{uuid.uuid4()}/adjust-status",
                headers={"Authorization": f"Bearer {token}"},
                json={"new_status": "REFUNDED", "reason": "Contournement"},
            )
        assert res.status_code == 400
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_adjust_status_success(legacy_admin_user):
    """Un admin avec 'finance.write' peut corriger un statut bloqué (ex: PENDING -> FAILED)."""
    txn = TransactionMobileMoney(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        montant=500,
        devise="XOF",
        operateur="WAVE",
        statut_paiement="PENDING",
        type_achat="pass_24h",
    )
    app.dependency_overrides[get_db] = _sequenced_db(
        [
            ("scalar", legacy_admin_user),
            ("scalar", txn),
        ]
    )
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/finance/transactions/{txn.id}/adjust-status",
                headers={"Authorization": f"Bearer {token}"},
                json={"new_status": "FAILED", "reason": "Webhook jamais reçu"},
            )
        assert res.status_code == 200
        assert txn.statut_paiement == "FAILED"
    finally:
        app.dependency_overrides[get_db] = mock_get_db
