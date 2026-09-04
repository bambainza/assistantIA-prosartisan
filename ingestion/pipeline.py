"""
Pipeline d'ingestion : PDF → Chunks sémantiques → Embeddings réels → Qdrant.

Usage CLI: python -m ingestion.pipeline --docs-dir ./ingestion/documents
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any

from pypdf import PdfReader
from qdrant_client.http.models import PointStruct

from app.config import settings
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

# Chevauchement cible entre deux chunks consécutifs, en proportion de
# chunk_size_words (AGENTS.md : chevauchement sémantique 10-15%).
DEFAULT_OVERLAP_RATIO = 0.12

# Champs de métadonnées obligatoires par document ingéré (AGENTS.md §3 :
# "Tagging sémantique strict").
REQUIRED_METADATA_FIELDS = (
    "metier_id",
    "secteur_id",
    "type_document",
    "niveau_expertise",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def extract_text_from_pdf(file_path: str) -> str:
    """Extrait le texte brut d'un fichier PDF."""
    reader = PdfReader(file_path)
    text_chunks: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text_chunks.append(extracted)
    return "\n\n".join(text_chunks)


def _split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases (heuristique simple, sans dépendance NLP)."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _tail_overlap(sentences: list[str], target_words: int) -> list[str]:
    """Retient les dernières phrases d'un chunk pour amorcer le chevauchement du suivant."""
    overlap: list[str] = []
    words = 0
    for sentence in reversed(sentences):
        if overlap and words >= target_words:
            break
        overlap.insert(0, sentence)
        words += len(sentence.split())
    return overlap


def chunk_text(
    text: str,
    chunk_size_words: int = 500,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[str]:
    """Découpe un texte en blocs sémantiques (phrases entières, jamais coupées en deux)
    d'environ `chunk_size_words` mots, avec un chevauchement d'environ `overlap_ratio`
    entre deux blocs consécutifs.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    overlap_words_target = max(1, int(chunk_size_words * overlap_ratio))
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current and current_words + sentence_words > chunk_size_words:
            chunks.append(" ".join(current))
            current = _tail_overlap(current, overlap_words_target)
            current_words = sum(len(s.split()) for s in current)
        current.append(sentence)
        current_words += sentence_words

    if current:
        chunks.append(" ".join(current))
    return chunks


def load_metadata(docs_dir: str) -> dict[str, Any]:
    """Charge les métadonnées par fichier depuis metadata.json (s'il existe dans docs_dir).

    Format attendu : ``{"nom_du_fichier.pdf": {"metier_id": 1, "secteur_id": 1,
    "type_document": "...", "niveau_expertise": "..."}, ...}``. Les valeurs
    présentes ici prévalent sur les valeurs par défaut passées à `run_ingestion`.
    """
    meta_path = os.path.join(docs_dir, "metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def resolve_and_validate_metadata(
    filename: str,
    overrides_by_file: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    """Fusionne les métadonnées par-fichier avec les valeurs par défaut du batch,
    puis vérifie que les champs obligatoires sont bien renseignés et cohérents.

    Lève ``ValueError`` (message destiné à l'admin) si une métadonnée requise
    manque ou est invalide.
    """
    merged = {**defaults, **overrides_by_file.get(filename, {})}

    manquants = [
        field for field in REQUIRED_METADATA_FIELDS if merged.get(field) in (None, "")
    ]
    if manquants:
        raise ValueError(
            f"{filename} : métadonnées obligatoires manquantes ({', '.join(manquants)})."
        )

    for field in ("metier_id", "secteur_id"):
        try:
            merged[field] = int(merged[field])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{filename} : '{field}' doit être un identifiant numérique."
            ) from exc
        if merged[field] <= 0:
            raise ValueError(f"{filename} : '{field}' doit être un entier positif.")

    merged["type_document"] = str(merged["type_document"]).strip()
    merged["niveau_expertise"] = str(merged["niveau_expertise"]).strip()
    return merged


def _point_id(document_name: str, chunk_index: int) -> str:
    """ID Qdrant déterministe : ré-ingérer le même document met à jour ses
    points existants au lieu d'en créer des doublons."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"prosartisan::{document_name}::{chunk_index}")
    )


async def run_ingestion(
    docs_dir: str = "./ingestion/documents",
    metier_id: int | None = 1,
    secteur_id: int | None = 1,
    type_document: str = "guide_technique",
    niveau_expertise: str = "intermédiaire",
) -> dict[str, Any]:
    """Exécute l'ingestion complète des PDF d'un dossier vers Qdrant.

    Utilise les embeddings réels de `rag_service` (mode mock inclus, via la
    même clé OPENAI_API_KEY) au lieu d'un vecteur factice, afin que la
    recherche sémantique soit effective une fois l'ingestion terminée.
    """
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        return {
            "status": "created_directory",
            "processed_files": 0,
            "ingested_chunks": 0,
            "erreurs": [],
        }

    await rag_service.ensure_collection()

    overrides_by_file = load_metadata(docs_dir)
    defaults = {
        "metier_id": metier_id,
        "secteur_id": secteur_id,
        "type_document": type_document,
        "niveau_expertise": niveau_expertise,
    }

    pdf_files = sorted(f for f in os.listdir(docs_dir) if f.endswith(".pdf"))
    total_chunks = 0
    processed_files = 0
    erreurs: list[str] = []

    for pdf in pdf_files:
        try:
            meta = resolve_and_validate_metadata(pdf, overrides_by_file, defaults)
        except ValueError as exc:
            erreurs.append(str(exc))
            continue

        path = os.path.join(docs_dir, pdf)
        try:
            text = extract_text_from_pdf(path)
        except Exception as exc:
            erreurs.append(f"{pdf} : lecture du PDF impossible ({exc}).")
            continue

        chunks = chunk_text(text)
        if not chunks:
            erreurs.append(f"{pdf} : aucun texte exploitable extrait du PDF.")
            continue

        points: list[PointStruct] = []
        for idx, chunk in enumerate(chunks):
            vector = await rag_service.get_embedding(chunk)
            payload = {
                "text": chunk,
                "document_name": pdf,
                "chunk_index": idx,
                **meta,
            }
            points.append(
                PointStruct(id=_point_id(pdf, idx), vector=vector, payload=payload)
            )

        try:
            await rag_service.qdrant_client.upsert(
                collection_name=settings.qdrant_collection,
                points=points,
            )
        except Exception as exc:
            erreurs.append(f"{pdf} : échec de l'indexation Qdrant ({exc}).")
            continue

        total_chunks += len(chunks)
        processed_files += 1
        logger.info("Document ingéré : %s (%d chunks).", pdf, len(chunks))

    status_val = "success"
    if erreurs and processed_files == 0:
        status_val = "error"
    elif erreurs:
        status_val = "partial"

    return {
        "status": status_val,
        "processed_files": processed_files,
        "ingested_chunks": total_chunks,
        "erreurs": erreurs,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Pipeline d'ingestion ProsArtisan")
    parser.add_argument(
        "--docs-dir", default="./ingestion/documents", help="Dossier contenant les PDF"
    )
    parser.add_argument("--metier-id", type=int, default=1, help="ID du métier")
    parser.add_argument("--secteur-id", type=int, default=1, help="ID du secteur")
    parser.add_argument("--type-document", default="guide_technique")
    parser.add_argument("--niveau-expertise", default="intermédiaire")
    args = parser.parse_args()

    resultat = asyncio.run(
        run_ingestion(
            docs_dir=args.docs_dir,
            metier_id=args.metier_id,
            secteur_id=args.secteur_id,
            type_document=args.type_document,
            niveau_expertise=args.niveau_expertise,
        )
    )
    print(f"Ingestion terminée: {resultat}")
