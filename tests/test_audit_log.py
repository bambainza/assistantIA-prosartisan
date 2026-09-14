"""Tests pour le journal d'audit des actions administrateur.

Régression sécurité : sans `require_permission("audit.read")`, un compte admin
restreint pourrait consulter le journal d'audit — un périmètre normalement
réservé aux rôles habilités à investiguer les actions des autres admins.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.audit_log import AuditLog
from app.models.role import Permission, Role
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def legacy_admin_user():
    return User(
        id=uuid.uuid4(),
        email="audit_admin@prosartisan.ci",
        nom="Admin Audit",
        telephone="+22507000020",
        is_admin=True,
        role_id=None,
    )


@pytest.fixture
def restricted_admin_user():
    """Admin avec un rôle RBAC qui n'accorde PAS 'audit.read'."""
    role = Role(id=uuid.uuid4(), code="support", label="Support Client")
    role.permissions = [Permission(id=uuid.uuid4(), code="packages.read")]
    user = User(
        id=uuid.uuid4(),
        email="support_no_audit@prosartisan.ci",
        nom="Admin Support Restreint",
        telephone="+22507000021",
        is_admin=True,
    )
    user.role = role
    return user


@pytest.fixture
def sample_audit_log(legacy_admin_user):
    return AuditLog(
        id=uuid.uuid4(),
        actor_id=legacy_admin_user.id,
        action="package.toggle",
        resource_type="package",
        resource_id=str(uuid.uuid4()),
        before_json=None,
        after_json={"est_actif": False},
        ip_address="127.0.0.1",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


@pytest.mark.asyncio
async def test_audit_read_accessible_admin_historique(
    legacy_admin_user, sample_audit_log
):
    """Un admin historique (sans rôle) peut consulter le journal d'audit."""

    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            stmt_str = str(stmt)
            mock_res = MagicMock()
            if "audit_logs" in stmt_str:
                mock_res.scalars.return_value.all.return_value = [sample_audit_log]
            else:
                mock_res.scalar_one_or_none.return_value = legacy_admin_user
            return mock_res

        session.execute = mock_execute
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/audit-logs", headers={"Authorization": f"Bearer {token}"}
            )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["action"] == "package.toggle"
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_audit_read_refuse_sans_permission(restricted_admin_user):
    """Un admin dont le rôle n'accorde pas 'audit.read' ne peut pas consulter le journal."""

    async def custom_mock_db():
        session = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = restricted_admin_user
        session.execute = AsyncMock(return_value=mock_res)
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(restricted_admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/audit-logs", headers={"Authorization": f"Bearer {token}"}
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_grant_pass_enregistre_une_entree_audit(legacy_admin_user):
    """L'attribution manuelle d'un Pass déclenche une écriture dans le journal d'audit."""
    added_objects: list = []

    async def custom_mock_db():
        session = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = legacy_admin_user
        session.execute = AsyncMock(return_value=mock_res)
        session.commit = AsyncMock()
        session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(legacy_admin_user.id)})
    target_user_id = str(uuid.uuid4())
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/admin/users/{target_user_id}/grant-pass?type_pass=pass_mois",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 200
        audit_entries = [o for o in added_objects if isinstance(o, AuditLog)]
        assert len(audit_entries) == 1
        assert audit_entries[0].action == "user.grant_pass"
        assert audit_entries[0].resource_id == target_user_id
    finally:
        app.dependency_overrides[get_db] = mock_get_db
