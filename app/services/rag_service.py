"""
Service RAG (Retrieval-Augmented Generation) & Multimodal.

Gère la recherche sémantique dans Qdrant (avec filtre metier_id),
l'assemblage du prompt système multilingue et l'appel à l'API LLM (OpenAI GPT-4o / GPT-4o-mini).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from openai import AsyncOpenAI
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


def load_system_prompt() -> str:
    """Charge le modèle de prompt système."""
    if os.path.exists(PROMPT_PATH):
        with open(PROMPT_PATH, encoding="utf-8") as f:
            return f.read()
    return (
        "Tu es l'Assistant Expert de ProsArtisan. Réponds de façon précise et technique.\n"
        "<CONTEXTE>\n{context}\n</CONTEXTE>\nQuestion : {question}"
    )


class RAGService:
    """Service de recherche vectorielle et de génération de réponse LLM."""

    def __init__(self) -> None:
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

    async def ensure_collection(self) -> None:
        """Crée la collection Qdrant si elle n'existe pas encore (idempotent).

        Sans cette étape, `/api/chat` en mode réel ne trouve jamais de contexte
        tant que personne n'a lancé l'ingestion manuellement : le RAG répondrait
        alors depuis les seules connaissances générales du LLM.
        """
        try:
            exists = await self.qdrant_client.collection_exists(
                settings.qdrant_collection
            )
            if exists:
                return
            await self.qdrant_client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(
                    size=settings.qdrant_vector_size, distance=Distance.COSINE
                ),
            )
            logger.info(
                "Collection Qdrant '%s' créée (taille=%d).",
                settings.qdrant_collection,
                settings.qdrant_vector_size,
            )
        except Exception as exc:
            logger.warning(
                "Qdrant indisponible, impossible de préparer la collection '%s' "
                "(%s). Le RAG répondra par le message de repli standard tant "
                "qu'aucun contexte ne peut être recherché.",
                settings.qdrant_collection,
                exc,
            )

    async def get_embedding(self, text: str) -> list[float]:
        """Génère un embedding vectoriel pour un texte donné avec mise en cache."""
        cached = await cache_service.get_cached_embedding(text)
        if cached is not None:
            return cached

        if (
            settings.openai_api_key.startswith("sk-placeholder")
            or settings.openai_api_key == "sk-placeholder"
        ):
            # Mode mock pour développement/test local sans clé API valide
            vec = [0.0] * 1536
            await cache_service.cache_embedding(text, vec)
            return vec

        response = await self.openai_client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        vec = response.data[0].embedding
        await cache_service.cache_embedding(text, vec)
        return vec

    async def search_context(
        self,
        query: str,
        metier_id: int | None = None,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """Recherche les passages pertinents dans Qdrant avec filtre optionnel par métier."""
        try:
            vector = await self.get_embedding(query)
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

            hits = await self.qdrant_client.search(
                collection_name=settings.qdrant_collection,
                query_vector=vector,
                query_filter=query_filter,
                limit=top_k,
            )
            return [
                {
                    "content": hit.payload.get("text", "") if hit.payload else "",
                    "metadata": hit.payload or {},
                    "score": hit.score,
                }
                for hit in hits
                # Sous le seuil, l'extrait est jugé hors sujet : mieux vaut ne
                # pas le fournir au LLM (garde-fou zéro hallucination).
                if hit.score >= settings.rag_min_score
            ]
        except Exception:
            # Fallback gracieux si Qdrant n'est pas encore disponible
            return []

    async def generate_response(
        self,
        question: str,
        metier_id: int | None = None,
        image_url: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Génère une réponse multimodale (texte + vision si image fournie)."""
        # Vérifier le cache pour les questions répétitives sans contexte d'image ni historique
        if not image_url and not history:
            cached_res = await cache_service.get_cached_rag_response(
                question=question, metier_id=metier_id
            )
            if cached_res is not None:
                return cached_res

        docs = await self.search_context(query=question, metier_id=metier_id)

        # Garde-fou "zéro hallucination" (AGENTS.md §3) : sans photo à analyser
        # (la vision GPT-4o peut juger une image sans document) et sans extrait
        # pertinent retrouvé, on ne laisse jamais le LLM inventer une règle de
        # chantier — on renvoie le message de repli standard sans l'appeler.
        if not image_url and not docs:
            fallback_res = {"reponse": FALLBACK_MESSAGE, "sources": []}
            if not history:
                await cache_service.cache_rag_response(
                    question=question, metier_id=metier_id, response=fallback_res
                )
            return fallback_res

        context_text = (
            "\n---\n".join([doc["content"] for doc in docs if doc.get("content")])
            if docs
            else "Aucun document spécifique trouvé."
        )

        system_prompt_template = load_system_prompt()
        prompt_formatted = system_prompt_template.format(
            context=context_text,
            question=question,
        )

        if (
            settings.openai_api_key.startswith("sk-placeholder")
            or settings.openai_api_key == "sk-placeholder"
        ):
            # Mode mock / test
            mock_reply = (
                f"Points clés techniques pour votre intervention :\n"
                f"1. Vérifiez la planéité et le niveau de la surface.\n"
                f"2. Respectez le dosage approprié (350 kg/m³ pour le mortier de pose).\n"
                f"3. Appliquez les consignes de sécurité sur le chantier.\n\n"
                f"(Réponse basée sur les documents métier {metier_id if metier_id else 'général'})"
            )
            mock_res = {
                "reponse": mock_reply,
                "sources": [doc["metadata"] for doc in docs if "metadata" in doc],
            }
            if not image_url and not history:
                await cache_service.cache_rag_response(
                    question=question, metier_id=metier_id, response=mock_res
                )
            return mock_res

        # Construction du message utilisateur (avec support vision GPT-4o si image)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt_formatted}
        ]

        if history:
            for item in history:
                messages.append({"role": item["role"], "content": item["content"]})

        if image_url:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Question de l'artisan: {question}"},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            )
            model_to_use = settings.llm_vision_model
        else:
            messages.append({"role": "user", "content": question})
            model_to_use = settings.llm_model

        completion = await self.openai_client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=settings.llm_temperature,
        )
        answer = completion.choices[0].message.content or ""

        final_res = {
            "reponse": answer,
            "sources": [doc["metadata"] for doc in docs if "metadata" in doc],
        }
        if not image_url and not history:
            await cache_service.cache_rag_response(
                question=question, metier_id=metier_id, response=final_res
            )
        return final_res

    async def generate_response_stream(
        self,
        question: str,
        metier_id: int | None = None,
        image_url: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[list[dict[str, Any]], Any]:
        """Recherche le contexte de connaissances puis retourne les fiches sources et le générateur du flux."""
        docs = await self.search_context(query=question, metier_id=metier_id)
        sources = [doc["metadata"] for doc in docs if "metadata" in doc]
        fallback_requis = not image_url and not docs

        async def _generator():
            if fallback_requis:
                # Garde-fou "zéro hallucination" : voir generate_response().
                for word in FALLBACK_MESSAGE.split(" "):
                    yield word + " "
                    await asyncio.sleep(0.02)
                return

            context_text = (
                "\n---\n".join([doc["content"] for doc in docs if doc.get("content")])
                if docs
                else "Aucun document spécifique trouvé."
            )

            system_prompt_template = load_system_prompt()
            prompt_formatted = system_prompt_template.format(
                context=context_text,
                question=question,
            )

            if (
                settings.openai_api_key.startswith("sk-placeholder")
                or settings.openai_api_key == "sk-placeholder"
            ):
                # Mode mock / test streaming
                mock_reply = (
                    f"Points clés techniques pour votre intervention :\n"
                    f"1. Vérifiez la planéité et le niveau de la surface.\n"
                    f"2. Respectez le dosage approprié (350 kg/m³ pour le mortier de pose).\n"
                    f"3. Appliquez les consignes de sécurité sur le chantier.\n\n"
                    f"(Réponse basée sur les fiches métier {metier_id if metier_id else 'général'})"
                )
                for word in mock_reply.split(" "):
                    yield word + " "
                    await asyncio.sleep(0.04)
                return

            # Construction du message utilisateur (avec support vision GPT-4o si image)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": prompt_formatted}
            ]

            if history:
                for item in history:
                    messages.append({"role": item["role"], "content": item["content"]})

            if image_url:
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Question de l'artisan: {question}",
                            },
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                )
                model_to_use = settings.llm_vision_model
            else:
                messages.append({"role": "user", "content": question})
                model_to_use = settings.llm_model

            completion = await self.openai_client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                temperature=settings.llm_temperature,
                stream=True,
            )
            async for chunk in completion:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        return sources, _generator()


rag_service = RAGService()
