"""Opérations fiables sur les documents de la base vectorielle."""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client.http.models import FieldCondition, Filter, MatchValue, UpdateStatus

from app.config import settings
from app.services.rag_service import rag_service


class DocumentVectorStoreError(RuntimeError):
    """La suppression n'a pas été confirmée par le stockage vectoriel."""


@dataclass(frozen=True)
class DocumentDeletionResult:
    """Résultat confirmé et sérialisable d'une suppression Qdrant."""

    operation_id: int | None
    status: str


class DocumentService:
    """Cycle de vie des documents techniques indexés."""

    async def delete_vectors(self, document_name: str) -> DocumentDeletionResult:
        """Supprime tous les chunks d'un document et attend la confirmation.

        L'opération par filtre est idempotente : supprimer de nouveau un
        document absent reste un succès confirmé par Qdrant.
        """
        try:
            result = await rag_service.qdrant_client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_name",
                            match=MatchValue(value=document_name),
                        )
                    ]
                ),
                wait=True,
            )
        except Exception as exc:
            raise DocumentVectorStoreError(
                "Le stockage vectoriel n'a pas pu supprimer le document."
            ) from exc

        if result.status != UpdateStatus.COMPLETED:
            raise DocumentVectorStoreError(
                f"Suppression Qdrant non confirmée (statut={result.status})."
            )
        return DocumentDeletionResult(
            operation_id=result.operation_id,
            status=result.status.value,
        )


document_service = DocumentService()
