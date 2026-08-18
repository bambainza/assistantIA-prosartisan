"""
Service RAG (Retrieval-Augmented Generation) & Multimodal.

Gère la recherche sémantique dans Qdrant (avec filtre metier_id),
l'assemblage du prompt système multilingue et l'appel à l'API LLM (OpenAI GPT-4o / GPT-4o-mini).
"""

from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.config import settings

# Charger le prompt système
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "system_prompt.txt")


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

    async def get_embedding(self, text: str) -> list[float]:
        """Génère un embedding vectoriel pour un texte donné."""
        if settings.openai_api_key.startswith("sk-placeholder") or settings.openai_api_key == "sk-placeholder":
            # Mode mock pour développement/test local sans clé API valide
            return [0.0] * 1536

        response = await self.openai_client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding

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
            ]
        except Exception:
            # Fallback gracieux si Qdrant n'est pas encore disponible
            return []

    async def generate_response(
        self,
        question: str,
        metier_id: int | None = None,
        image_url: str | None = None,
    ) -> dict[str, Any]:
        """Génère une réponse multimodale (texte + vision si image fournie)."""
        docs = await self.search_context(query=question, metier_id=metier_id)

        context_text = "\n---\n".join(
            [doc["content"] for doc in docs if doc.get("content")]
        ) if docs else "Aucun document spécifique trouvé."

        system_prompt_template = load_system_prompt()
        prompt_formatted = system_prompt_template.format(
            context=context_text,
            question=question,
        )

        if settings.openai_api_key.startswith("sk-placeholder") or settings.openai_api_key == "sk-placeholder":
            # Mode mock / test
            mock_reply = (
                f"Points clés techniques pour votre intervention :\n"
                f"1. Vérifiez la planéité et le niveau de la surface.\n"
                f"2. Respectez le dosage approprié (350 kg/m³ pour le mortier de pose).\n"
                f"3. Appliquez les consignes de sécurité sur le chantier.\n\n"
                f"(Réponse basée sur les documents métier {metier_id if metier_id else 'général'})"
            )
            return {
                "reponse": mock_reply,
                "sources": [doc["metadata"] for doc in docs if "metadata" in doc],
            }

        # Construction du message utilisateur (avec support vision GPT-4o si image)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt_formatted}
        ]

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

        return {
            "reponse": answer,
            "sources": [doc["metadata"] for doc in docs if "metadata" in doc],
        }


rag_service = RAGService()
