"""Tests de l'orchestration multi-fournisseurs LLM (Mistral AI & Google Gemini),
de la bascule automatique (failover), du coupe-circuit (circuit breaker) et
du pilotage back-office (`/api/admin/parametres/llm-providers`).
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.audit_log import AuditLog
from app.models.role import Permission, Role
from app.models.user import User
from app.services.calculator_service import calculator_service
from app.services.llm_provider_service import (
    PROVIDER_GEMINI,
    PROVIDER_MISTRAL,
    build_gemini_interaction_payload,
    llm_provider_service,
    normalize_gemini_model,
)
from app.services.rag_service import rag_service
from tests.conftest import mock_get_db

DOC = {
    "content": "Dosage béton fondations : 350 kg/m³.",
    "metadata": {"document_name": "guide_beton.md"},
}


@pytest.fixture
def rag_context(monkeypatch):
    """Fournit un contexte RAG valide et active un métier pour tester les appels LLM."""

    async def _search(**kwargs):
        return [DOC]

    async def _actif(metier_id):
        return True

    monkeypatch.setattr(rag_service, "search_context", _search)
    monkeypatch.setattr(rag_service, "is_metier_active", _actif)


def test_normalize_gemini_model_remplace_les_modeles_deprecies():
    """Tout modèle Gemini déprécié (1.5, 2.0, 2.5, 3.5-flash) est remplacé par gemini-3.8-flash."""
    assert normalize_gemini_model("gemini-2.0-flash") == "gemini-3.8-flash"
    assert normalize_gemini_model("gemini-1.5-pro") == "gemini-3.8-flash"
    assert normalize_gemini_model("gemini-2.5-flash") == "gemini-3.8-flash"
    assert normalize_gemini_model("gemini-3.5-flash") == "gemini-3.8-flash"
    # Les modèles actuels (gemini-3.8-flash, gemini-3.5-flash-lite, gemini-4-carbon) sont conservés
    assert normalize_gemini_model("gemini-3.8-flash") == "gemini-3.8-flash"
    assert normalize_gemini_model("gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"
    assert normalize_gemini_model("gemini-4-carbon") == "gemini-4-carbon"


def test_build_gemini_interaction_payload_vision_et_outils():
    """Vérifie la conversion des messages (système, image base64, outils) vers `/v1beta/interactions`."""
    messages = [
        {"role": "system", "content": "Tu es ProsArtisan."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyse cette fissure"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
                },
            ],
        },
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calcul_beton",
                "description": "Calcule le volume",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    payload = build_gemini_interaction_payload(
        model="gemini-3.8-flash",
        messages=messages,
        tools=tools,
        stream=False,
    )
    assert payload["model"] == "gemini-3.8-flash"
    assert payload["system_instruction"] == "Tu es ProsArtisan."
    assert payload["store"] is False
    assert "temperature" not in payload["generation_config"]
    assert payload["generation_config"]["thinking_level"] in (
        "minimal",
        "low",
        "medium",
        "high",
    )
    assert payload["tools"][0]["name"] == "calcul_beton"
    user_step = payload["input"][0]
    assert user_step["type"] == "user_input"
    assert user_step["content"][1] == {
        "type": "image",
        "mime_type": "image/png",
        "data": "iVBORw0KGgo=",
    }


@pytest.mark.asyncio
async def test_selection_automatique_et_coupe_circuit(monkeypatch):
    """En mode auto, le fournisseur en cooldown est dépriorisé au profit du fournisseur sain."""
    monkeypatch.setattr(settings, "mistral_api_key", "sk-real-mistral")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-real-gemini")
    monkeypatch.setattr(settings, "llm_circuit_breaker_threshold", 2)
    await llm_provider_service.reset_health()
    await llm_provider_service.set_routing_config(mode="auto", failover_enabled=True)

    # Par défaut, les deux sont à 100% de stabilité : Mistral puis Gemini
    order_initial = await llm_provider_service.get_candidate_providers()
    assert order_initial == [PROVIDER_MISTRAL, PROVIDER_GEMINI]

    # Deux échecs consécutifs sur Mistral déclenchent son coupe-circuit (cooldown)
    await llm_provider_service.record_failure(PROVIDER_MISTRAL, "HTTP 503 Unavailable")
    await llm_provider_service.record_failure(PROVIDER_MISTRAL, "HTTP 503 Unavailable")

    mistral_status = await llm_provider_service.get_provider_status(PROVIDER_MISTRAL)
    gemini_status = await llm_provider_service.get_provider_status(PROVIDER_GEMINI)
    assert mistral_status["status"] == "cooldown"
    assert gemini_status["status"] == "healthy"
    assert gemini_status["stability_score"] > mistral_status["stability_score"]

    # Le routeur sélectionne désormais Gemini en premier
    order_after = await llm_provider_service.get_candidate_providers()
    assert order_after == [PROVIDER_GEMINI, PROVIDER_MISTRAL]


@pytest.mark.asyncio
async def test_rag_bascule_automatique_mistral_vers_gemini(monkeypatch, rag_context):
    """Si Mistral échoue (ex. 429/503), `generate_response` bascule automatiquement sur Gemini."""
    monkeypatch.setattr(settings, "mistral_api_key", "sk-real-mistral")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-real-gemini")
    await llm_provider_service.reset_health()
    await llm_provider_service.set_routing_config(mode="mistral", failover_enabled=True)

    # Mistral échoue
    mistral_chat = MagicMock()
    mistral_chat.complete_async = AsyncMock(
        side_effect=RuntimeError("Mistral 429 Rate limit exceeded")
    )
    monkeypatch.setattr(rag_service, "mistral_client", MagicMock(chat=mistral_chat))

    # Gemini répond via l'API Interactions
    def _gemini_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/interactions")
        assert request.headers.get("Api-Revision") == "2026-05-20"
        return httpx.Response(
            200,
            json={
                "id": "inter_123",
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {
                                "type": "text",
                                "text": "Dosage recommandé par Gemini : 350 kg/m³.",
                            }
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        llm_provider_service,
        "_http_transport",
        httpx.MockTransport(_gemini_handler),
    )

    result = await rag_service.generate_response(
        question="Quel dosage pour fondation ?", metier_id=1
    )

    assert result["reponse"] == "Dosage recommandé par Gemini : 350 kg/m³."
    assert result["sources"] == [DOC["metadata"]]

    # Vérifie que l'échec Mistral et le succès Gemini ont été comptabilisés
    st_mistral = await llm_provider_service.get_provider_status(PROVIDER_MISTRAL)
    st_gemini = await llm_provider_service.get_provider_status(PROVIDER_GEMINI)
    assert st_mistral["consecutive_failures"] == 1
    assert st_gemini["total_successes"] == 1


@pytest.mark.asyncio
async def test_rag_gemini_avec_appel_calculateur(monkeypatch, rag_context):
    """Gemini peut déclencher un calculateur métier (`function_call` -> `function_result`)."""
    monkeypatch.setattr(settings, "mistral_api_key", "sk-placeholder")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-real-gemini")
    await llm_provider_service.reset_health()
    await llm_provider_service.set_routing_config(mode="gemini", failover_enabled=True)

    executions = []

    def _exec_tool(name, args):
        executions.append((name, args))
        return {"volume_m3": 3.0, "sacs_ciment": 21}

    monkeypatch.setattr(calculator_service, "execute_tool", _exec_tool)

    call_count = 0

    def _gemini_tool_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content.decode("utf-8"))
        if call_count == 1:
            return httpx.Response(
                200,
                json={
                    "id": "inter_tool_1",
                    "status": "requires_action",
                    "steps": [
                        {
                            "type": "function_call",
                            "id": "gcall_1",
                            "name": "calculer_dosage_beton_mortier",
                            "arguments": {"longueur_m": 6, "largeur_m": 5},
                        }
                    ],
                },
            )
        # 2e appel : vérifie que le résultat de l'outil est bien présent dans `input`
        steps_in = body["input"]
        fn_res = [s for s in steps_in if s.get("type") == "function_result"]
        assert len(fn_res) == 1
        assert fn_res[0]["call_id"] == "gcall_1"
        assert fn_res[0]["result"] == {"volume_m3": 3.0, "sacs_ciment": 21}
        return httpx.Response(
            200,
            json={
                "id": "inter_tool_2",
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {
                                "type": "text",
                                "text": "Pour 3 m³, prévoyez 21 sacs de ciment.",
                            }
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        llm_provider_service,
        "_http_transport",
        httpx.MockTransport(_gemini_tool_handler),
    )

    result = await rag_service.generate_response(
        question="Combien de sacs pour ma dalle 6x5 ?", metier_id=1
    )

    assert result["reponse"] == "Pour 3 m³, prévoyez 21 sacs de ciment."
    assert executions == [
        ("calculer_dosage_beton_mortier", {"longueur_m": 6, "largeur_m": 5})
    ]


@pytest.mark.asyncio
async def test_rag_stream_bascule_gemini_vers_mistral(monkeypatch, rag_context):
    """En streaming, si Gemini échoue à l'ouverture, bascule transparente sur Mistral."""
    monkeypatch.setattr(settings, "mistral_api_key", "sk-real-mistral")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-real-gemini")
    await llm_provider_service.reset_health()
    await llm_provider_service.set_routing_config(mode="gemini", failover_enabled=True)

    # Gemini renvoie HTTP 503
    def _gemini_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    monkeypatch.setattr(
        llm_provider_service,
        "_http_transport",
        httpx.MockTransport(_gemini_fail),
    )

    # Mistral streame la réponse de secours
    async def _mistral_stream(**kwargs):
        async def _gen():
            for chunk in ("Secours ", "Mistral ", "OK."):
                delta = SimpleNamespace(content=chunk, tool_calls=None)
                yield SimpleNamespace(
                    data=SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
                )

        return _gen()

    mistral_chat = MagicMock()
    mistral_chat.stream_async = _mistral_stream
    monkeypatch.setattr(rag_service, "mistral_client", MagicMock(chat=mistral_chat))

    sources, gen = await rag_service.generate_response_stream(
        question="Question streaming avec secours", metier_id=1
    )
    texte = "".join([c async for c in gen])

    assert texte == "Secours Mistral OK."
    assert sources == [DOC["metadata"]]


@pytest.mark.asyncio
async def test_admin_llm_providers_endpoints_rbac_et_audit():
    """Vérifie les routes back-office `/api/admin/parametres/llm-providers` (RBAC + AuditLog)."""
    admin_user = User(
        id=uuid.uuid4(),
        email="admin_llm@prosartisan.ci",
        nom="Admin IA",
        is_admin=True,
        role_id=None,
    )
    restricted_role = Role(id=uuid.uuid4(), code="lecteur_seul", label="Lecteur")
    restricted_role.permissions = [Permission(id=uuid.uuid4(), code="actualites.read")]
    restricted_user = User(
        id=uuid.uuid4(),
        email="restricted_llm@prosartisan.ci",
        nom="Restreint",
        is_admin=True,
    )
    restricted_user.role = restricted_role

    admin_token = create_access_token(
        {"sub": str(admin_user.id), "email": admin_user.email}
    )
    restricted_token = create_access_token(
        {"sub": str(restricted_user.id), "email": restricted_user.email}
    )

    added_objects: list[object] = []

    async def _custom_db():
        session = MagicMock()

        async def _execute(stmt):
            res = MagicMock()
            stmt_str = str(stmt)
            if "restricted_llm" in stmt_str or str(restricted_user.id) in stmt_str:
                res.scalar_one_or_none.return_value = restricted_user
            else:
                res.scalar_one_or_none.return_value = admin_user
            return res

        session.execute = _execute
        session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        session.commit = AsyncMock()
        yield session

    # 1. Utilisateur restreint sans `parametres.read` -> 403
    async def _restricted_db():
        session = MagicMock()
        res = MagicMock()
        res.scalar_one_or_none.return_value = restricted_user
        session.execute = AsyncMock(return_value=res)
        yield session

    app.dependency_overrides[get_db] = _restricted_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_forbidden = await client.get(
                "/api/admin/parametres/llm-providers",
                headers={"Authorization": f"Bearer {restricted_token}"},
            )
        assert r_forbidden.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db

    # 2. Admin autorisé : lecture, bascule vers Gemini, puis réinitialisation santé avec AuditLog
    app.dependency_overrides[get_db] = _custom_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_get = await client.get(
                "/api/admin/parametres/llm-providers",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert r_get.status_code == 200
            data_get = r_get.json()
            assert "providers" in data_get
            assert {p["code"] for p in data_get["providers"]} == {"MISTRAL", "GEMINI"}

            r_put = await client.put(
                "/api/admin/parametres/llm-providers",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"mode": "gemini", "failover_enabled": True},
            )
            assert r_put.status_code == 200
            data_put = r_put.json()
            assert data_put["mode"] == "gemini"
            assert data_put["failover_enabled"] is True

            r_reset = await client.post(
                "/api/admin/parametres/llm-providers/reset-health",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert r_reset.status_code == 200

        audit_entries = [obj for obj in added_objects if isinstance(obj, AuditLog)]
        actions = [a.action for a in audit_entries]
        assert "parametres.llm_provider.update" in actions
        assert "parametres.llm_provider.reset_health" in actions
    finally:
        app.dependency_overrides[get_db] = mock_get_db
