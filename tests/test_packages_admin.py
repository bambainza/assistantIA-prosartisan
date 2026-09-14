"""Tests unitaires et d'intégration pour le module de gestion des packages et abonnements."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.package import Package
from app.models.quota import QuotaUtilisateur
from app.models.subscription import UserSubscription
from app.models.user import User


@pytest.fixture
def admin_user():
    """Artisan avec privilèges administrateur."""
    return User(
        id=uuid.uuid4(),
        email="admin_pkg@prosartisan.ci",
        nom="Admin Packages",
        telephone="+22507000001",
        is_admin=True,
    )


@pytest.fixture
def artisan_user():
    """Artisan standard."""
    return User(
        id=uuid.uuid4(),
        email="artisan@prosartisan.ci",
        nom="Kouamé Laurent",
        telephone="+22507000002",
        is_admin=False,
        type_abonnement="FREE",
    )


@pytest.fixture
def sample_package():
    """Package modèle de test."""
    return Package(
        id=uuid.uuid4(),
        code="pass_mois",
        nom="Pass Mensuel Pro",
        description="Formule complète 30 jours",
        prix=3000,
        devise="XOF",
        type_package="DURATION",
        duree_jours=30,
        quota_requetes=999999,
        auto_renouvelable=True,
        est_actif=True,
        fonctionnalites=["Questions illimitées 30 jours"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )


@pytest.fixture
def sample_subscription(artisan_user, sample_package):
    """Souscription modèle de test."""
    now = datetime.now(UTC).replace(tzinfo=None)
    sub = UserSubscription(
        id=uuid.uuid4(),
        user_id=artisan_user.id,
        package_id=sample_package.id,
        statut="ACTIVE",
        date_debut=now,
        date_fin=now + timedelta(days=30),
        quota_initial=999999,
        quota_consomme=5,
        renouvellement_auto=True,
        created_at=now,
        updated_at=now,
    )
    sub.user = artisan_user
    sub.package = sample_package
    return sub


@pytest.fixture
def mock_db_with_packages(admin_user, artisan_user, sample_package, sample_subscription):
    """Fournit un mock AsyncSession complet pour tester le cycle de vie des packages."""
    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            stmt_str = str(stmt)
            mock_res = MagicMock()

            # Requête utilisateur admin
            if "User.is_admin" in stmt_str or "users.is_admin" in stmt_str:
                mock_res.scalar_one_or_none.return_value = admin_user
                mock_res.scalar.return_value = 1
            elif "packages" in stmt_str and "SELECT count" not in stmt_str:
                mock_res.scalar_one_or_none.return_value = sample_package
                mock_res.scalars.return_value.all.return_value = [sample_package]
            elif "user_subscriptions" in stmt_str and "SELECT count" not in stmt_str:
                mock_res.scalar_one_or_none.return_value = sample_subscription
                mock_res.scalars.return_value.all.return_value = [sample_subscription]
                mock_res.all.return_value = [
                    (sample_subscription, artisan_user, sample_package, "Maçonnerie & Gros Œuvre")
                ]
            elif "quotas_utilisateurs" in stmt_str:
                quota = QuotaUtilisateur(user_id=artisan_user.id, requetes_restantes_gratuites=5)
                mock_res.scalar_one_or_none.return_value = quota
            else:
                mock_res.scalar_one_or_none.return_value = sample_package
                mock_res.scalar.return_value = 1
                mock_res.scalars.return_value.all.return_value = [sample_package]
                mock_res.all.return_value = [
                    (sample_subscription, artisan_user, sample_package, "Maçonnerie & Gros Œuvre")
                ]

            return mock_res

        session.execute = mock_execute
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    yield
    from tests.conftest import mock_get_db
    app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_admin_list_packages(mock_db_with_packages, admin_user):
    """GET /api/admin/packages doit retourner la liste des packages avec token admin."""
    token = create_access_token(data={"sub": str(admin_user.id)})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/admin/packages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "packages" in data
        assert len(data["packages"]) >= 1
        assert data["packages"][0]["code"] == "pass_mois"


@pytest.mark.asyncio
async def test_admin_create_and_toggle_package(mock_db_with_packages, admin_user):
    """Vérifie la création, modification et bascule d'activation d'un package."""
    token = create_access_token(data={"sub": str(admin_user.id)})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Création
        create_payload = {
            "code": "pass_vip_chantier",
            "nom": "Pass Spécial Chantier Grand Bassam",
            "description": "Offre temporaire pour chantiers côtiers",
            "prix": 4500,
            "devise": "XOF",
            "type_package": "DURATION",
            "duree_jours": 45,
            "quota_requetes": 999999,
            "auto_renouvelable": False,
            "est_actif": True,
            "fonctionnalites": ["Accès complet 45 jours"],
        }
        res_create = await client.post(
            "/api/admin/packages",
            headers={"Authorization": f"Bearer {token}"},
            json=create_payload,
        )
        assert res_create.status_code in (201, 400)

        # 2. Toggle activation
        dummy_pkg_id = uuid.uuid4()
        res_toggle = await client.patch(
            f"/api/admin/packages/{dummy_pkg_id}/toggle",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_toggle.status_code == 200
        assert "est_actif" in res_toggle.json()


@pytest.mark.asyncio
async def test_admin_assign_and_manage_subscription(mock_db_with_packages, admin_user, artisan_user):
    """Vérifie l'attribution, la consultation, la prolongation et la résiliation d'une souscription."""
    token = create_access_token(data={"sub": str(admin_user.id)})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Assigner le Pass
        assign_payload = {
            "user_id": str(artisan_user.id),
            "package_code": "pass_mois",
            "renouvellement_auto": True,
        }
        res_assign = await client.post(
            "/api/admin/subscriptions/assign",
            headers={"Authorization": f"Bearer {token}"},
            json=assign_payload,
        )
        assert res_assign.status_code == 200
        assert res_assign.json()["status"] == "success"

        # 2. Consulter la liste
        res_list = await client.get(
            "/api/admin/subscriptions?statut=ACTIVE",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_list.status_code == 200
        assert "subscriptions" in res_list.json()

        # 3. Prolonger l'abonnement
        sub_id = uuid.uuid4()
        res_extend = await client.post(
            f"/api/admin/subscriptions/{sub_id}/extend",
            headers={"Authorization": f"Bearer {token}"},
            json={"jours_supplementaires": 15},
        )
        assert res_extend.status_code == 200

        # 4. Résilier l'abonnement
        res_cancel = await client.post(
            f"/api/admin/subscriptions/{sub_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_cancel.status_code == 200


@pytest.mark.asyncio
async def test_admin_subscriptions_stats(mock_db_with_packages, admin_user):
    """Vérifie la route des statistiques KPIs des souscriptions."""
    token = create_access_token(data={"sub": str(admin_user.id)})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_stats = await client.get(
            "/api/admin/subscriptions/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_stats.status_code == 200
        kpis = res_stats.json()["kpis"]
        assert "total_inscrits" in kpis
        assert "total_abonnements" in kpis
        assert "abonnements_actifs" in kpis


@pytest.mark.asyncio
async def test_non_admin_forbidden_on_packages(artisan_user):
    """Vérifie qu'un artisan non-admin ne peut pas accéder aux routes packages."""
    async def non_admin_db():
        session = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None  # Non admin
        session.execute = AsyncMock(return_value=mock_res)
        yield session

    app.dependency_overrides[get_db] = non_admin_db
    token = create_access_token(data={"sub": str(artisan_user.id)})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/admin/packages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403

        res_sub = await client.get(
            "/api/admin/subscriptions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_sub.status_code == 403

    from tests.conftest import mock_get_db
    app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_admin_update_and_manage_package_lifecycle(mock_db_with_packages, admin_user, sample_package):
    """Vérifie la modification, la désactivation, la réactivation et la suppression d'un package."""
    token = create_access_token(data={"sub": str(admin_user.id)})
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Modification (PUT)
        update_payload = {
            "nom": "Pass Mensuel Pro Ajusté",
            "prix": 3500,
            "type_package": "DURATION",
            "description": "Tarif mis à jour pour inflation",
            "fonctionnalites": ["Support prioritaire WhatsApp", "Devis illimités"],
        }
        res_update = await client.put(
            f"/api/admin/packages/{sample_package.id}",
            headers={"Authorization": f"Bearer {token}"},
            json=update_payload,
        )
        assert res_update.status_code == 200
        data_update = res_update.json()
        assert data_update["package"]["nom"] == "Pass Mensuel Pro Ajusté"
        assert data_update["package"]["prix"] == 3500

        # 2. Désactivation explicite (active=false)
        res_deact = await client.patch(
            f"/api/admin/packages/{sample_package.id}/toggle?active=false",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_deact.status_code == 200
        assert res_deact.json()["est_actif"] is False
        assert "désactivé" in res_deact.json()["message"]

        # 3. Réactivation explicite (active=true)
        res_react = await client.patch(
            f"/api/admin/packages/{sample_package.id}/toggle?active=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_react.status_code == 200
        assert res_react.json()["est_actif"] is True
        assert "activé" in res_react.json()["message"]

        # 4. Suppression avec force=True
        res_delete = await client.delete(
            f"/api/admin/packages/{sample_package.id}?force=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_delete.status_code == 200
        assert res_delete.json()["status"] == "success"
        assert "supprimé" in res_delete.json()["message"]
