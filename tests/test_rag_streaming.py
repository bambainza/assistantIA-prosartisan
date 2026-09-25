"""Tests du RAG : streaming avec calculateurs, cache, états d'activation, embeddings par lots."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.services.cache_service import cache_service
from app.services.calculator_service import calculator_service
from app.services.rag_service import FALLBACK_MESSAGE, rag_service

DOC = {"content": "Béton : 350 kg/m³.", "metadata": {"document_name": "guide.md"}}


def _event(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(data=SimpleNamespace(choices=[SimpleNamespace(delta=delta)]))


def _tool_delta(index, name=None, arguments=None, call_id=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class _FakeStreamingChat:
    """Faux `mistral_client.chat` : rejoue une liste de flux, un par appel."""

    def __init__(self, streams):
        self._streams = list(streams)
        self.calls = []

    async def stream_async(self, **kwargs):
        self.calls.append(kwargs)
        events = self._streams.pop(0)

        async def _gen():
            for ev in events:
                yield ev

        return _gen()


@pytest.fixture
def mode_reel(monkeypatch):
    """Désactive le mode mock (clé Mistral « valide ») et fournit un contexte RAG."""
    monkeypatch.setattr(settings, "mistral_api_key", "sk-test-reel")

    async def _search(**kwargs):
        return [DOC]

    monkeypatch.setattr(rag_service, "search_context", _search)

    async def _actif(metier_id):
        return True

    monkeypatch.setattr(rag_service, "is_metier_active", _actif)


async def _collecter(gen):
    return "".join([c async for c in gen])


@pytest.mark.asyncio
async def test_stream_execute_les_calculateurs(monkeypatch, mode_reel):
    """Un appel d'outil fragmenté dans le flux est reconstitué, exécuté, puis la réponse finale est streamée."""
    executions = []

    def _execute(name, args):
        executions.append((name, args))
        return {"volume_m3": 2.5}

    monkeypatch.setattr(calculator_service, "execute_tool", _execute)
    chat = _FakeStreamingChat(
        [
            [
                _event(
                    tool_calls=[_tool_delta(0, "calcul_beton", '{"longueur"', "c1")]
                ),
                _event(tool_calls=[_tool_delta(0, None, ': 5, "largeur": 1}')]),
            ],
            [_event("Il vous faut "), _event("2,5 m³.")],
        ]
    )
    monkeypatch.setattr(rag_service, "mistral_client", MagicMock(chat=chat))

    sources, gen = await rag_service.generate_response_stream(
        question="Combien de béton pour ma dalle ?", metier_id=1
    )
    texte = await _collecter(gen)

    assert texte == "Il vous faut 2,5 m³."
    assert executions == [("calcul_beton", {"longueur": 5, "largeur": 1})]
    assert "tools" in chat.calls[0]
    assert "tools" not in chat.calls[1]
    tool_msg = chat.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "c1"
    assert json.loads(tool_msg["content"]) == {"volume_m3": 2.5}
    assert sources == [DOC["metadata"]]


@pytest.mark.asyncio
async def test_stream_met_en_cache_et_resert_sans_llm(monkeypatch, mode_reel):
    chat = _FakeStreamingChat([[_event("Réponse "), _event("complète.")]])
    monkeypatch.setattr(rag_service, "mistral_client", MagicMock(chat=chat))

    _, gen = await rag_service.generate_response_stream(question="Q cache", metier_id=2)
    assert await _collecter(gen) == "Réponse complète."

    # 2e appel identique : servi depuis le cache, sans nouvel appel LLM.
    sources, gen2 = await rag_service.generate_response_stream(
        question="Q cache", metier_id=2
    )
    assert (await _collecter(gen2)).strip() == "Réponse complète."
    assert len(chat.calls) == 1
    assert sources == [DOC["metadata"]]


@pytest.mark.asyncio
async def test_stream_repli_zero_hallucination_sans_llm(monkeypatch):
    async def _vide(**kwargs):
        return []

    monkeypatch.setattr(rag_service, "search_context", _vide)
    chat = _FakeStreamingChat([])
    monkeypatch.setattr(rag_service, "mistral_client", MagicMock(chat=chat))
    monkeypatch.setattr(settings, "mistral_api_key", "sk-test-reel")

    sources, gen = await rag_service.generate_response_stream(question="Hors sujet")

    assert (await _collecter(gen)).strip() == FALLBACK_MESSAGE
    assert sources == []
    assert chat.calls == []


@pytest.mark.asyncio
async def test_invalidation_perime_les_reponses_en_cache():
    await cache_service.cache_rag_response(
        question="Q", metier_id=1, response={"reponse": "ancienne", "sources": []}
    )
    assert await cache_service.get_cached_rag_response(question="Q", metier_id=1)

    await rag_service.invalidate_activation_cache()
    version = await rag_service._config_version()

    assert version != "0"
    assert (
        await cache_service.get_cached_rag_response(
            question="Q", metier_id=1, version=version
        )
        is None
    )


@pytest.mark.asyncio
async def test_etats_d_activation_mis_en_cache(monkeypatch):
    """Les métiers désactivés ne sont lus en base qu'une fois par TTL (et relus après invalidation)."""
    lectures = []

    async def _loader_compte():
        lectures.append(1)
        return {3}

    original = rag_service._cached_set

    async def _cached_set(key, loader):
        return await original(key, _loader_compte)

    monkeypatch.setattr(rag_service, "_cached_set", _cached_set)

    assert await rag_service.is_metier_active(3) is False
    assert await rag_service.is_metier_active(1) is True
    assert len(lectures) == 1

    await rag_service.invalidate_activation_cache()
    await rag_service.is_metier_active(3)
    assert len(lectures) == 2


@pytest.mark.asyncio
async def test_embeddings_par_lots(monkeypatch):
    monkeypatch.setattr(settings, "mistral_api_key", "sk-test-reel")
    appels = []

    async def _create(model, inputs):
        appels.append(list(inputs))
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[float(len(t))]) for t in inputs]
        )

    client = MagicMock()
    client.embeddings.create_async = _create
    monkeypatch.setattr(rag_service, "mistral_client", client)

    textes = [f"chunk {i}" * (i + 1) for i in range(20)]
    await cache_service.cache_embedding(textes[0], [42.0])  # déjà en cache

    vecteurs = await rag_service.get_embeddings(textes)

    assert vecteurs[0] == [42.0]
    assert vecteurs[5] == [float(len(textes[5]))]
    assert [len(a) for a in appels] == [16, 3]  # 19 textes absents du cache
