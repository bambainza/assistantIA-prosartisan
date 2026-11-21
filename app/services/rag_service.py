"""
Service RAG (Retrieval-Augmented Generation) & Multimodal.

Gère la recherche sémantique dans Qdrant (avec filtre metier_id),
l'assemblage du prompt système multilingue et l'appel à l'API LLM
(Mistral Small/Medium — vision intégrée nativement dans les modèles 3.x).

Les modes réponse complète (`generate_response`) et streaming
(`generate_response_stream`) partagent la même préparation (métier suspendu,
cache, garde-fou zéro hallucination, prompt, calculateurs) : un mode ne doit
jamais offrir moins de garanties que l'autre.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from mistralai.client import Mistral
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    VectorParams,
)

from app.config import settings
from app.services.cache_service import cache_service
from app.services.calculator_service import calculator_service
from app.services.llm_provider_service import (
    PROVIDER_GEMINI,
    PROVIDER_MISTRAL,
    LLMToolCall,
    llm_provider_service,
)

logger = logging.getLogger(__name__)

# Charger le prompt système
PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "prompts", "system_prompt.txt"
)

# Message de repli standard (garde-fou "zéro hallucination", AGENTS.md §3) —
# doit rester identique à la consigne donnée au LLM dans system_prompt.txt.
FALLBACK_MESSAGE = (
    "Les documents techniques actuels de ProsArtisan ne contiennent pas cette "
    "information spécifique pour votre métier. Souhaitez-vous reformuler votre question ?"
)

METIER_SUSPENDU_MESSAGE = (
    "Ce domaine métier est actuellement suspendu ou en cours d'actualisation "
    "technique par l'administration. Veuillez sélectionner un autre métier ou "
    "réessayer ultérieurement."
)

# États d'activation (métiers, documents) mis en cache dans Redis : sans cela,
# chaque question déclenchait deux requêtes SQL. Invalidés par les routes admin
# via `invalidate_activation_cache()` ; le TTL borne l'obsolescence sinon.
_ACTIVATION_CACHE_TTL_SECONDS = 60
_INACTIVE_DOCS_KEY = "prosartisan:rag_config:inactive_docs"
_INACTIVE_METIERS_KEY = "prosartisan:rag_config:inactive_metiers"
# Version incrémentée à chaque changement d'activation : elle fait partie de la
# clé des réponses RAG en cache, ce qui périme d'un coup toutes les réponses
# citant un document ou un métier qui vient d'être désactivé.
_CONFIG_VERSION_KEY = "prosartisan:rag_config:version"
_CONFIG_VERSION_TTL_SECONDS = 30 * 86400

# Usage d'un vecteur : document indexé ou question de recherche.
TACHE_DOCUMENT = "document"
TACHE_REQUETE = "requete"

# Taille des lots d'embeddings (≈ 16 × 450 mots, sous la limite de tokens
# d'une requête `mistral-embed`).
EMBEDDING_BATCH_SIZE = 16


class RechercheIndisponibleError(RuntimeError):
    """La recherche documentaire (embedding ou Qdrant) a échoué.

    À distinguer d'une recherche aboutie sans résultat : seule cette dernière
    autorise le message de repli « zéro hallucination ».
    """


class ActivationIndisponibleError(RechercheIndisponibleError):
    """Les droits d'utilisation du corpus ne peuvent pas être vérifiés."""


def load_system_prompt() -> str:
    """Charge le modèle de prompt système."""
    if os.path.exists(PROMPT_PATH):
        with open(PROMPT_PATH, encoding="utf-8") as f:
            return f.read()
    return (
        "Tu es l'Assistant Expert de ProsArtisan. Réponds de façon précise et technique.\n"
        "<CONTEXTE>\n{context}\n</CONTEXTE>\nQuestion : {question}"
    )


MOCK_REPLY_NOTICE = (
    "[Mode démonstration : aucune IA n'est configurée sur ce serveur. "
    "Cette réponse générique n'est pas issue des documents techniques.]"
)


def _mock_reply(metier_id: int | None) -> str:
    """Réponse de démonstration (dev/tests sans clé IA), jamais mise en cache.

    Impossible en production : le démarrage y exige au moins une clé IA
    (`Settings._verifier_secrets_production`).
    """
    return (
        "Points clés techniques pour votre intervention :\n"
        "1. Vérifiez la planéité et le niveau de la surface.\n"
        "2. Respectez le dosage approprié (350 kg/m³ pour le mortier de pose).\n"
        "3. Appliquez les consignes de sécurité sur le chantier.\n\n"
        f"{MOCK_REPLY_NOTICE}"
    )


# Reformulation de la requête de recherche (questions en nouchi, dioula,
# baoulé, bété) : mise en cache par question pour ne payer l'appel qu'une fois.
_REFORMULATION_CACHE_PREFIX = "prosartisan:rag:reformulation:"
_REFORMULATION_TTL_SECONDS = 7 * 86400
_REFORMULATION_MAX_CHARS = 300
REFORMULATION_PROMPT = (
    "Tu prépares une recherche documentaire pour des artisans de Côte d'Ivoire. "
    "La question peut être écrite en français, en nouchi (argot ivoirien), en "
    "dioula, en baoulé ou en bété, ou mélanger ces langues. Réécris-la en une "
    "seule requête de recherche en français technique standard (termes du "
    "métier, sans argot). N'ajoute aucune information absente de la question, "
    "ne réponds pas à la question. Renvoie uniquement la requête, sur une ligne."
)


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, str):
        return json.loads(arguments) if arguments.strip() else {}
    return dict(arguments or {})


@dataclass
class _ToolCall:
    """Appel d'outil normalisé (réponse complète ou reconstitué depuis un flux)."""

    id: str
    name: str
    arguments: str = ""


@dataclass
class _Preparation:
    """Résultat de la préparation commune aux deux modes de génération."""

    sources: list[dict[str, Any]]
    # Réponse finale connue sans appeler le LLM (métier suspendu, cache, repli).
    immediate: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    tools: list[dict[str, Any]] | None = None
    cacheable: bool = False
    cache_version: str = "0"


class RAGService:
    """Service de recherche vectorielle et de génération de réponse LLM."""

    def __init__(self) -> None:
        self.mistral_client = Mistral(api_key=settings.mistral_api_key)
        self.qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

    @staticmethod
    def _is_mock_mode() -> bool:
        """Mode mock (dev/tests) : ni Mistral ni Gemini n'ont de clé API valide configurée."""
        return not llm_provider_service.is_any_provider_configured()

    @staticmethod
    def _is_embedding_mock_mode() -> bool:
        """Vrai si le fournisseur de vecteurs actif (`EMBEDDING_PROVIDER`) n'a pas de clé valide."""
        return not llm_provider_service.is_provider_configured(
            settings.embedding_provider
        )

    async def ensure_collection(self) -> None:
        """Crée la collection Qdrant du modèle de vecteurs actif si elle manque.

        Sans cette étape, `/api/chat` en mode réel ne trouve jamais de contexte
        tant que personne n'a lancé l'ingestion manuellement : le RAG répondrait
        alors depuis les seules connaissances générales du LLM. Une collection
        existante d'une autre dimension est signalée (journal d'erreur) : elle
        appartient à un autre modèle et doit être réindexée.
        """
        collection = settings.collection_vectorielle
        taille = settings.embedding_dimensions
        try:
            if await self.qdrant_client.collection_exists(collection):
                info = await self.qdrant_client.get_collection(collection)
                taille_existante = getattr(
                    getattr(getattr(info, "config", None), "params", None),
                    "vectors",
                    None,
                )
                taille_existante = getattr(taille_existante, "size", None)
                if isinstance(taille_existante, int) and taille_existante != taille:
                    logger.error(
                        "La collection Qdrant '%s' contient des vecteurs de dimension "
                        "%d, mais le modèle actif (%s) produit %d dimensions : "
                        "réindexer le corpus avec `python -m ingestion.pipeline`.",
                        collection,
                        taille_existante,
                        settings.espace_embeddings,
                        taille,
                    )
                return
            await self.qdrant_client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=taille, distance=Distance.COSINE),
            )
            logger.info(
                "Collection Qdrant '%s' créée (taille=%d, modèle %s).",
                collection,
                taille,
                settings.espace_embeddings,
            )
        except Exception as exc:
            logger.warning(
                "Qdrant indisponible, impossible de préparer la collection '%s' "
                "(%s). Tant que la recherche reste impossible, les questions "
                "reçoivent une erreur 503 et sont rendues (repli standard en "
                "mode mock uniquement).",
                collection,
                exc,
            )

    # ── Embeddings ──

    async def get_embedding(self, text: str, tache: str = TACHE_REQUETE) -> list[float]:
        """Vecteur d'un texte (par défaut une question de recherche), avec cache."""
        return (await self.get_embeddings([text], tache=tache))[0]

    async def get_embeddings(
        self, texts: list[str], tache: str = TACHE_DOCUMENT
    ) -> list[list[float]]:
        """Vecteurs d'une liste de textes, par lots, avec mise en cache.

        Fournisseur : `EMBEDDING_PROVIDER` (`gemini-embedding-001` par défaut,
        ou `mistral-embed`). `tache` distingue les documents indexés
        (`TACHE_DOCUMENT`, défaut, ingestion) des questions
        (`TACHE_REQUETE`, recherche) : Gemini les encode différemment. La
        même fonction sert à l'ingestion et à la recherche (cohérence des
        vecteurs, AGENTS.md §3). Seuls les textes absents du cache sont
        envoyés, par lots de `EMBEDDING_BATCH_SIZE`.
        """
        if tache not in (TACHE_DOCUMENT, TACHE_REQUETE):
            raise ValueError(f"Tâche de vecteur inconnue : {tache}")
        gemini = settings.embedding_provider == PROVIDER_GEMINI
        # Mistral n'a pas de vecteur propre aux questions : même espace pour les deux.
        espace = (
            f"{settings.espace_embeddings}:{tache}"
            if gemini
            else settings.espace_embeddings
        )

        results: list[list[float] | None] = [
            await cache_service.get_cached_embedding(t, espace=espace) for t in texts
        ]
        missing = [i for i, vec in enumerate(results) if vec is None]

        for start in range(0, len(missing), EMBEDDING_BATCH_SIZE):
            batch_idx = missing[start : start + EMBEDDING_BATCH_SIZE]
            batch_texts = [texts[i] for i in batch_idx]
            if self._is_embedding_mock_mode():
                vectors = [[0.0] * settings.embedding_dimensions for _ in batch_texts]
            elif gemini:
                vectors = await llm_provider_service.embed_gemini(
                    batch_texts,
                    task_type=(
                        "RETRIEVAL_QUERY"
                        if tache == TACHE_REQUETE
                        else "RETRIEVAL_DOCUMENT"
                    ),
                )
            else:
                response = await self.mistral_client.embeddings.create_async(
                    model=settings.embedding_model,
                    inputs=batch_texts,
                )
                vectors = [item.embedding for item in response.data]
            for i, vec in zip(batch_idx, vectors, strict=True):
                results[i] = vec
                await cache_service.cache_embedding(texts[i], vec, espace=espace)

        return [vec for vec in results if vec is not None]

    # ── États d'activation (cache Redis) ──

    async def _cached_set(self, key: str, loader: Any) -> set[Any]:
        try:
            cached = await cache_service.get(key)
            if cached is not None:
                return set(json.loads(cached))
        except Exception as exc:
            logger.warning("Lecture du cache d'activation impossible (%s).", exc)

        values = await loader()
        try:
            await cache_service.set(
                key,
                json.dumps(sorted(values, key=str)),
                ttl_seconds=_ACTIVATION_CACHE_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("Écriture du cache d'activation impossible (%s).", exc)
        return values

    async def get_inactive_document_names(self) -> set[str]:
        """Retourne l'ensemble des noms de fichiers désactivés par l'administration."""

        async def _load() -> set[str]:
            try:
                from sqlalchemy import select

                from app.db.session import async_session
                from app.models.document_config import DocumentConfig

                async with async_session() as session:
                    stmt = select(DocumentConfig.filename).where(
                        DocumentConfig.is_active == False
                    )
                    res = await session.execute(stmt)
                    return {row[0] for row in res.all()}
            except Exception as exc:
                raise ActivationIndisponibleError(
                    "Vérification des activations indisponible."
                ) from exc

        return await self._cached_set(_INACTIVE_DOCS_KEY, _load)

    async def get_inactive_metier_ids(self) -> set[int]:
        """Retourne l'ensemble des identifiants de métiers désactivés."""

        async def _load() -> set[int]:
            try:
                from sqlalchemy import select

                from app.db.session import async_session
                from app.models.metier import Metier

                async with async_session() as session:
                    stmt = select(Metier.id).where(Metier.is_active == False)
                    res = await session.execute(stmt)
                    return {int(row[0]) for row in res.all()}
            except Exception as exc:
                raise ActivationIndisponibleError(
                    "Vérification des activations indisponible."
                ) from exc

        return await self._cached_set(_INACTIVE_METIERS_KEY, _load)

    async def is_metier_active(self, metier_id: int | None) -> bool:
        """Vérifie si un métier est actif (un métier inconnu est considéré actif)."""
        if metier_id is None:
            return True
        return metier_id not in await self.get_inactive_metier_ids()

    async def invalidate_activation_cache(self) -> None:
        """À appeler après toute (dés)activation d'un métier ou d'un document.

        Vide les ensembles mis en cache et change la version des réponses RAG
        en cache, pour qu'aucune réponse ne cite un document désactivé.
        """
        try:
            await cache_service.delete(_INACTIVE_DOCS_KEY)
            await cache_service.delete(_INACTIVE_METIERS_KEY)
            await cache_service.increment(
                _CONFIG_VERSION_KEY, _CONFIG_VERSION_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning("Invalidation du cache d'activation impossible (%s).", exc)

    async def _config_version(self) -> str:
        try:
            return await cache_service.get(_CONFIG_VERSION_KEY) or "0"
        except Exception:
            return "0"

    # ── Recherche ──

    async def search_context(
        self,
        query: str,
        metier_id: int | None = None,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """Recherche les passages pertinents dans Qdrant avec filtre optionnel par métier et exclusion des documents désactivés.

        Une liste vide signifie « recherche aboutie, aucun extrait pertinent ».
        Une panne (embedding Mistral, Qdrant) lève `RechercheIndisponibleError` :
        elle ne doit jamais être confondue avec une absence d'information.
        """
        try:
            vector = await self.get_embedding(query, tache=TACHE_REQUETE)
            query_filter = None
            if metier_id is not None:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="metier_id",
                            match=MatchValue(value=metier_id),
                        )
                    ]
                )

            response = await self.qdrant_client.query_points(
                collection_name=settings.collection_vectorielle,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )

            inactive_docs = await self.get_inactive_document_names()

            hits = [
                {
                    "content": hit.payload.get("text", "") if hit.payload else "",
                    "metadata": hit.payload or {},
                    "score": hit.score,
                }
                for hit in response.points
                # Sous le seuil, l'extrait est jugé hors sujet : mieux vaut ne
                # pas le fournir au LLM (garde-fou zéro hallucination).
                if hit.score >= settings.rag_min_score
                and (hit.payload or {}).get("document_name") not in inactive_docs
            ]

            if not hits and self._is_embedding_mock_mode() and not self._is_mock_mode():
                hits = await self._lexical_search_qdrant(
                    query=query,
                    query_filter=query_filter,
                    inactive_docs=inactive_docs,
                    top_k=top_k,
                )

            return hits
        except ActivationIndisponibleError:
            raise
        except Exception as exc:
            raise RechercheIndisponibleError(
                f"Recherche documentaire impossible ({type(exc).__name__}: {exc})"
            ) from exc

    @staticmethod
    def _tokenize_search_text(text: str) -> set[str]:
        """Normalise et découpe un texte en mots-clés significatifs (>= 3 lettres, sans accents)."""
        stop_words = {
            "les",
            "des",
            "une",
            "pour",
            "dans",
            "sur",
            "avec",
            "par",
            "est",
            "son",
            "ses",
            "aux",
            "quel",
            "quelle",
            "quels",
            "quelles",
            "comment",
            "cote",
            "ivoire",
            "mon",
            "ton",
            "nos",
            "vos",
            "que",
            "qui",
            "quoi",
        }
        normalized = (
            unicodedata.normalize("NFKD", text.lower())
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        words = re.findall(r"[a-z0-9]{3,}", normalized)
        return {w for w in words if w not in stop_words}

    async def _lexical_search_qdrant(
        self,
        *,
        query: str,
        query_filter: Filter | None,
        inactive_docs: set[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Recherche lexicale de secours dans Qdrant lorsque seul Gemini est configuré (sans clé `mistral-embed`)."""
        query_tokens = self._tokenize_search_text(query)
        if not query_tokens:
            return []

        points, _ = await self.qdrant_client.scroll(
            collection_name=settings.collection_vectorielle,
            scroll_filter=query_filter,
            limit=500,
            with_payload=True,
            with_vectors=False,
        )

        scored: list[dict[str, Any]] = []
        for pt in points:
            payload = pt.payload or {}
            doc_name = payload.get("document_name")
            if doc_name in inactive_docs:
                continue
            text = str(payload.get("text", ""))
            if not text:
                continue
            doc_tokens = self._tokenize_search_text(text)
            overlap = query_tokens & doc_tokens
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_tokens))
            # Un seul mot commun sur une question longue ne prouve rien : il
            # faut à la fois une part suffisante des mots-clés et un minimum
            # de mots communs (borné par la taille de la question).
            min_overlap = min(settings.rag_lexical_min_overlap, len(query_tokens))
            if score >= settings.rag_lexical_min_score and len(overlap) >= min_overlap:
                scored.append(
                    {
                        "content": text,
                        "metadata": payload,
                        "score": round(score, 4),
                    }
                )

        scored.sort(key=lambda item: float(item["score"]), reverse=True)
        return scored[:top_k]

    # ── Reformulation multilingue de la requête de recherche ──

    async def reformuler_requete(self, question: str) -> str | None:
        """Réécrit la question en français technique pour la recherche seule.

        Le LLM reçoit toujours la question d'origine ; seule la recherche
        vectorielle profite de la reformulation. Retourne `None` si la
        reformulation est désactivée, en mode mock, identique à la question ou
        impossible (un échec du fournisseur n'est pas une panne de recherche :
        la question d'origine reste cherchée).
        """
        if not settings.rag_reformulation_requete or self._is_mock_mode():
            return None

        cle = (
            _REFORMULATION_CACHE_PREFIX
            + hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()
        )
        try:
            cached = await cache_service.get(cle)
        except Exception:
            cached = None
        if cached is not None:
            return cached or None

        try:
            brut = await llm_provider_service.complete_text_with_failover(
                messages=[
                    {"role": "system", "content": REFORMULATION_PROMPT},
                    {"role": "user", "content": question},
                ],
                mistral_client=self.mistral_client,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("Reformulation de la requête impossible (%s).", exc)
            return None

        reformulee = " ".join(brut.split())[:_REFORMULATION_MAX_CHARS].strip(" \"'")
        if not reformulee or reformulee.lower() == question.strip().lower():
            reformulee = ""
        try:
            await cache_service.set(
                cle, reformulee, ttl_seconds=_REFORMULATION_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning("Mise en cache de la reformulation impossible (%s).", exc)
        return reformulee or None

    async def _rechercher(
        self, question: str, metier_id: int | None, top_k: int = 4
    ) -> list[dict[str, Any]]:
        """Cherche la question d'origine et, si utile, sa reformulation française.

        Les extraits des deux recherches sont fusionnés (meilleur score par
        extrait) : une reformulation maladroite ne peut pas masquer un extrait
        trouvé par la question d'origine. Chaque recherche applique le même
        seuil `RAG_MIN_SCORE`.
        """
        docs = await self.search_context(query=question, metier_id=metier_id)
        reformulee = await self.reformuler_requete(question)
        if not reformulee:
            return docs

        docs_reformulee = await self.search_context(
            query=reformulee, metier_id=metier_id
        )
        fusion: dict[str, dict[str, Any]] = {}
        for doc in [*docs, *docs_reformulee]:
            cle = str(doc.get("content", ""))
            courant = fusion.get(cle)
            if courant is None or float(doc.get("score", 0)) > float(
                courant.get("score", 0)
            ):
                fusion[cle] = doc
        return sorted(
            fusion.values(), key=lambda d: float(d.get("score", 0)), reverse=True
        )[:top_k]

    # ── Préparation commune ──

    def _build_messages(
        self,
        question: str,
        docs: list[dict[str, Any]],
        image_url: str | None,
        history: list[dict[str, str]] | None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Assemble prompt système + historique + question (vision si photo)."""
        context_text = (
            "\n---\n".join([doc["content"] for doc in docs if doc.get("content")])
            if docs
            else "Aucun document spécifique trouvé."
        )
        prompt_formatted = load_system_prompt().format(
            context=context_text,
            question=question,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt_formatted}
        ]
        for item in history or []:
            messages.append({"role": item["role"], "content": item["content"]})

        if image_url:
            # Même format `image_url` qu'OpenAI, accepté tel quel par la SDK Mistral.
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Question de l'artisan: {question}"},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            )
            return messages, settings.llm_vision_model

        messages.append({"role": "user", "content": question})
        return messages, settings.llm_model

    async def _prepare(
        self,
        question: str,
        metier_id: int | None,
        image_url: str | None,
        history: list[dict[str, str]] | None,
    ) -> _Preparation:
        # Vérifier les droits avant de servir une ancienne réponse en cache.
        await self.get_inactive_document_names()
        if metier_id is not None and not await self.is_metier_active(metier_id):
            return _Preparation(sources=[], immediate=METIER_SUSPENDU_MESSAGE)

        # Cache des questions répétitives, sans photo ni historique.
        cacheable = not image_url and not history
        version = await self._config_version() if cacheable else "0"
        if cacheable:
            cached = await cache_service.get_cached_rag_response(
                question=question, metier_id=metier_id, version=version
            )
            if cached is not None:
                return _Preparation(
                    sources=cached.get("sources", []), immediate=cached["reponse"]
                )

        try:
            docs = await self._rechercher(question, metier_id)
        except RechercheIndisponibleError as exc:
            # Mode réel : la panne remonte au routeur (503 + question rendue).
            # Répondre « pas d'information » serait faux, et le mettre en cache
            # figerait cette fausse réponse pendant 24 h.
            if isinstance(exc, ActivationIndisponibleError) or not self._is_mock_mode():
                raise
            # Mode mock (dev/tests sans Qdrant) : repli servi, jamais mis en cache.
            logger.warning("%s — repli servi sans mise en cache (mode mock).", exc)
            return _Preparation(sources=[], immediate=FALLBACK_MESSAGE)
        sources = [doc["metadata"] for doc in docs if "metadata" in doc]

        # Garde-fou "zéro hallucination" (AGENTS.md §3) : sans photo à analyser
        # (la vision peut juger une image sans document) et sans extrait
        # pertinent retrouvé, on ne laisse jamais le LLM inventer une règle de
        # chantier — on renvoie le message de repli standard sans l'appeler.
        if not image_url and not docs:
            prep = _Preparation(
                sources=[],
                immediate=FALLBACK_MESSAGE,
                cacheable=cacheable,
                cache_version=version,
            )
            await self._cache_if_needed(prep, question, metier_id, FALLBACK_MESSAGE)
            return prep

        messages, model = self._build_messages(question, docs, image_url, history)
        return _Preparation(
            sources=sources,
            messages=messages,
            model=model,
            # Les calculateurs certifiés ne s'appliquent pas à l'analyse photo.
            tools=calculator_service.get_tool_definitions() if not image_url else None,
            cacheable=cacheable,
            cache_version=version,
        )

    async def _cache_if_needed(
        self,
        prep: _Preparation,
        question: str,
        metier_id: int | None,
        answer: str,
    ) -> None:
        if not prep.cacheable:
            return
        await cache_service.cache_rag_response(
            question=question,
            metier_id=metier_id,
            response={"reponse": answer, "sources": prep.sources},
            version=prep.cache_version,
        )

    def _append_tool_turn(
        self,
        messages: list[dict[str, Any]],
        tool_calls: list[_ToolCall],
        assistant_content: str = "",
    ) -> None:
        """Exécute les calculateurs demandés et ajoute le tour d'outil aux messages."""
        messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            try:
                result: Any = calculator_service.execute_tool(
                    tc.name, _parse_arguments(tc.arguments)
                )
            except Exception as exc:
                logger.warning(
                    "Erreur lors de l'exécution de l'outil %s: %s", tc.name, exc
                )
                result = {"tool": tc.name, "error": str(exc)}
            messages.append(
                {
                    "role": "tool",
                    "name": tc.name,
                    "content": json.dumps(result),
                    "tool_call_id": tc.id,
                }
            )

    # ── Réponse complète (Mistral & Gemini avec bascule automatique) ──

    async def _complete_with_mistral(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> str:
        """Exécute la complétion non-streamée via Mistral (avec tour d'outils éventuel)."""
        completion = await self.mistral_client.chat.complete_async(
            model=model,
            messages=messages,
            tools=tools,
            temperature=settings.llm_temperature,
        )
        choice = completion.choices[0]
        raw_tool_calls = getattr(choice.message, "tool_calls", None)

        if raw_tool_calls:
            tool_calls = [
                _ToolCall(
                    id=getattr(tc, "id", None) or f"call_{i}",
                    name=tc.function.name,
                    arguments=tc.function.arguments
                    if isinstance(tc.function.arguments, str)
                    else json.dumps(tc.function.arguments),
                )
                for i, tc in enumerate(raw_tool_calls)
            ]
            self._append_tool_turn(messages, tool_calls, choice.message.content or "")
            completion2 = await self.mistral_client.chat.complete_async(
                model=model,
                messages=messages,
                temperature=settings.llm_temperature,
            )
            return completion2.choices[0].message.content or ""

        return choice.message.content or ""

    async def _complete_with_gemini(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        is_vision: bool,
    ) -> str:
        """Exécute la complétion non-streamée via Google Gemini Interactions API."""
        result = await llm_provider_service.complete_gemini(
            messages=messages,
            tools=tools,
            is_vision=is_vision,
        )
        if result.tool_calls:
            tool_calls = [
                _ToolCall(
                    id=tc.id,
                    name=tc.name,
                    arguments=tc.arguments,
                )
                for tc in result.tool_calls
            ]
            self._append_tool_turn(messages, tool_calls, result.content)
            result2 = await llm_provider_service.complete_gemini(
                messages=messages,
                tools=None,
                is_vision=is_vision,
            )
            return result2.content

        return result.content

    async def generate_response(
        self,
        question: str,
        metier_id: int | None = None,
        image_url: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Génère une réponse multimodale (texte + vision) avec bascule Mistral <-> Gemini."""
        prep = await self._prepare(question, metier_id, image_url, history)
        if prep.immediate is not None:
            return {"reponse": prep.immediate, "sources": prep.sources}

        if self._is_mock_mode():
            # Réponse de démonstration : jamais mise en cache (elle survivrait
            # à la configuration d'une vraie clé IA).
            return {"reponse": _mock_reply(metier_id), "sources": prep.sources}

        candidates = await llm_provider_service.get_candidate_providers()
        if not candidates:
            candidates = [PROVIDER_MISTRAL]

        last_exc: Exception | None = None
        for idx, provider in enumerate(candidates):
            messages_copy = copy.deepcopy(prep.messages)
            t0 = time.perf_counter()
            try:
                if provider == PROVIDER_GEMINI:
                    answer = await self._complete_with_gemini(
                        messages=messages_copy,
                        tools=prep.tools,
                        is_vision=bool(image_url),
                    )
                else:
                    answer = await self._complete_with_mistral(
                        model=prep.model,
                        messages=messages_copy,
                        tools=prep.tools,
                    )
                latency_ms = (time.perf_counter() - t0) * 1000.0
                await llm_provider_service.record_success(provider, latency_ms)
                await self._cache_if_needed(prep, question, metier_id, answer)
                return {"reponse": answer, "sources": prep.sources}
            except Exception as exc:
                last_exc = exc
                await llm_provider_service.record_failure(provider, exc)
                if idx + 1 < len(candidates):
                    logger.warning(
                        "Échec du fournisseur LLM '%s' (%s) — bascule automatique vers '%s'.",
                        provider,
                        exc,
                        candidates[idx + 1],
                    )
                    continue
                raise

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Aucun fournisseur LLM disponible.")

    # ── Streaming (Mistral & Gemini avec bascule automatique) ──

    async def generate_response_stream(
        self,
        question: str,
        metier_id: int | None = None,
        image_url: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[list[dict[str, Any]], AsyncIterator[str]]:
        """Prépare la réponse puis retourne les sources et le générateur du flux.

        Mêmes garanties que `generate_response` : métier suspendu, cache,
        repli zéro hallucination, calculateurs et bascule automatique entre
        Mistral et Gemini. La réponse complète est mise en cache en fin de flux.
        """
        prep = await self._prepare(question, metier_id, image_url, history)

        async def _stream_words(text: str, delay: float) -> AsyncIterator[str]:
            for word in text.split(" "):
                yield word + " "
                await asyncio.sleep(delay)

        async def _generator() -> AsyncIterator[str]:
            if prep.immediate is not None:
                async for chunk in _stream_words(prep.immediate, 0.02):
                    yield chunk
                return

            if self._is_mock_mode():
                # Démonstration sans clé IA : jamais mise en cache.
                async for chunk in _stream_words(_mock_reply(metier_id), 0.04):
                    yield chunk
                return

            candidates = await llm_provider_service.get_candidate_providers()
            if not candidates:
                candidates = [PROVIDER_MISTRAL]

            for idx, provider in enumerate(candidates):
                messages_copy = copy.deepcopy(prep.messages)
                parts: list[str] = []
                tool_calls: list[_ToolCall] = []
                t0 = time.perf_counter()
                try:
                    stream_gen = (
                        self._stream_completion_gemini(
                            messages_copy,
                            prep.tools,
                            tool_calls,
                            is_vision=bool(image_url),
                        )
                        if provider == PROVIDER_GEMINI
                        else self._stream_completion(
                            prep.model, messages_copy, prep.tools, tool_calls
                        )
                    )
                    async for chunk in stream_gen:
                        parts.append(chunk)
                        yield chunk

                    if tool_calls:
                        self._append_tool_turn(
                            messages_copy, tool_calls, "".join(parts)
                        )
                        stream_gen2 = (
                            self._stream_completion_gemini(
                                messages_copy,
                                None,
                                [],
                                is_vision=bool(image_url),
                            )
                            if provider == PROVIDER_GEMINI
                            else self._stream_completion(
                                prep.model, messages_copy, None, []
                            )
                        )
                        async for chunk in stream_gen2:
                            parts.append(chunk)
                            yield chunk

                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    await llm_provider_service.record_success(provider, latency_ms)
                    await self._cache_if_needed(
                        prep, question, metier_id, "".join(parts)
                    )
                    return
                except Exception as exc:
                    await llm_provider_service.record_failure(provider, exc)
                    if idx + 1 < len(candidates) and not parts:
                        logger.warning(
                            "Échec streaming LLM '%s' (%s) — bascule automatique vers '%s'.",
                            provider,
                            exc,
                            candidates[idx + 1],
                        )
                        continue
                    raise

        return prep.sources, _generator()

    async def _stream_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_calls_out: list[_ToolCall],
    ) -> AsyncIterator[str]:
        """Streame le texte d'une complétion Mistral et collecte ses éventuels appels d'outil."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": settings.llm_temperature,
        }
        if tools:
            kwargs["tools"] = tools

        stream = await self.mistral_client.chat.stream_async(**kwargs)
        pending: dict[int, _ToolCall] = {}
        async for event in stream:
            delta = event.data.choices[0].delta
            for pos, tc in enumerate(getattr(delta, "tool_calls", None) or []):
                index = getattr(tc, "index", None)
                index = pos if index is None else index
                current = pending.setdefault(
                    index, _ToolCall(id=f"call_{index}", name="")
                )
                if getattr(tc, "id", None):
                    current.id = tc.id
                if tc.function.name:
                    current.name = tc.function.name
                args = tc.function.arguments
                if args:
                    current.arguments += (
                        args if isinstance(args, str) else json.dumps(args)
                    )
            content = delta.content
            if isinstance(content, str) and content:
                yield content

        tool_calls_out.extend(pending[i] for i in sorted(pending))

    async def _stream_completion_gemini(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_calls_out: list[_ToolCall],
        is_vision: bool = False,
    ) -> AsyncIterator[str]:
        """Streame le texte d'une complétion Google Gemini et collecte ses éventuels appels d'outil."""
        gemini_tools_out: list[LLMToolCall] = []
        async for chunk in llm_provider_service.stream_gemini(
            messages=messages,
            tools=tools,
            tool_calls_out=gemini_tools_out,
            is_vision=is_vision,
        ):
            yield chunk

        for tc in gemini_tools_out:
            tool_calls_out.append(
                _ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
            )


rag_service = RAGService()
