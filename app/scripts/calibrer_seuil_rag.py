"""
Calibrage de `RAG_MIN_SCORE` sur le corpus réellement indexé.

Pour chaque question du jeu d'évaluation (questions couvertes par le corpus et
questions hors corpus), mesure le meilleur score cosinus renvoyé par Qdrant,
sans seuil. Recommande ensuite le seuil le plus bas qui laisse passer au plus
`--max-faux-positifs` des questions hors corpus (garde-fou « zéro
hallucination » d'abord), et indique la part de questions couvertes encore
servies à ce seuil, au total et par langue.

Prérequis : clé valide du fournisseur de vecteurs (`EMBEDDING_PROVIDER`,
Gemini par défaut : mêmes vecteurs que l'ingestion) et collection Qdrant
correspondante alimentée. Lecture seule : aucune écriture en base ni dans
Qdrant.

Usage :
    python -m app.scripts.calibrer_seuil_rag \
        [--jeu ingestion/evaluation/questions_seuil_rag.jsonl] \
        [--max-faux-positifs 0.05] [--avec-reformulation] [--json rapport.json]

`--avec-reformulation` mesure aussi la question reformulée en français
technique (comme `/api/chat`) et retient le meilleur des deux scores.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JEU_PAR_DEFAUT = (
    Path(__file__).resolve().parents[2]
    / "ingestion"
    / "evaluation"
    / "questions_seuil_rag.jsonl"
)
ATTENDUS = {"couvert", "hors_corpus"}


@dataclass(frozen=True)
class QuestionEvaluation:
    question: str
    attendu: str
    langue: str = "fr"
    document: str | None = None


@dataclass
class Recommandation:
    seuil: float
    taux_faux_positifs: float
    taux_couvertes_servies: float
    couvertes_servies_par_langue: dict[str, float] = field(default_factory=dict)
    nb_couvertes: int = 0
    nb_hors_corpus: int = 0


def charger_jeu(chemin: Path) -> list[QuestionEvaluation]:
    """Lit le jeu JSONL et valide chaque ligne (erreur explicite sinon)."""
    questions: list[QuestionEvaluation] = []
    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        try:
            brut = json.loads(ligne)
            q = QuestionEvaluation(
                question=str(brut["question"]).strip(),
                attendu=str(brut["attendu"]),
                langue=str(brut.get("langue", "fr")),
                document=brut.get("document"),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"{chemin}:{numero} : ligne invalide ({exc}).") from exc
        if q.attendu not in ATTENDUS or not q.question:
            raise ValueError(
                f"{chemin}:{numero} : 'attendu' doit valoir couvert ou hors_corpus."
            )
        questions.append(q)
    return questions


def recommander_seuil(
    resultats: Sequence[tuple[QuestionEvaluation, float]],
    max_faux_positifs: float = 0.05,
    pas: float = 0.01,
) -> Recommandation:
    """Seuil le plus bas dont le taux d'acceptation hors corpus ≤ `max_faux_positifs`.

    Une question est « servie » si son meilleur score ≥ seuil. À seuil égal de
    sécurité, le plus bas maximise les questions couvertes encore servies.
    """
    couvertes = [(q, s) for q, s in resultats if q.attendu == "couvert"]
    hors = [s for q, s in resultats if q.attendu == "hors_corpus"]
    if not couvertes or not hors:
        raise ValueError("Le jeu doit contenir des questions couvertes et hors corpus.")

    nb_pas = round(1 / pas)
    for i in range(nb_pas + 1):
        seuil = round(i * pas, 4)
        faux_positifs = sum(1 for s in hors if s >= seuil) / len(hors)
        if faux_positifs <= max_faux_positifs:
            break
    else:  # pragma: no cover - seuil = 1.0 atteint toujours 0 faux positif
        seuil = 1.0
        faux_positifs = 0.0

    par_langue: dict[str, list[bool]] = {}
    for q, s in couvertes:
        par_langue.setdefault(q.langue, []).append(s >= seuil)

    return Recommandation(
        seuil=seuil,
        taux_faux_positifs=round(faux_positifs, 4),
        taux_couvertes_servies=round(
            sum(1 for _, s in couvertes if s >= seuil) / len(couvertes), 4
        ),
        couvertes_servies_par_langue={
            langue: round(sum(v) / len(v), 4)
            for langue, v in sorted(par_langue.items())
        },
        nb_couvertes=len(couvertes),
        nb_hors_corpus=len(hors),
    )


async def _meilleur_score(requete: str) -> float:
    from app.config import settings
    from app.services.rag_service import TACHE_REQUETE, rag_service

    vecteur = await rag_service.get_embedding(requete, tache=TACHE_REQUETE)
    reponse = await rag_service.qdrant_client.query_points(
        collection_name=settings.collection_vectorielle,
        query=vecteur,
        limit=1,
        with_payload=False,
    )
    return float(reponse.points[0].score) if reponse.points else 0.0


async def mesurer_scores(
    questions: Sequence[QuestionEvaluation], avec_reformulation: bool
) -> list[tuple[QuestionEvaluation, float]]:
    from app.services.rag_service import rag_service

    resultats: list[tuple[QuestionEvaluation, float]] = []
    for q in questions:
        score = await _meilleur_score(q.question)
        if avec_reformulation:
            reformulee = await rag_service.reformuler_requete(q.question)
            if reformulee:
                score = max(score, await _meilleur_score(reformulee))
        resultats.append((q, score))
    return resultats


def _afficher(
    resultats: Sequence[tuple[QuestionEvaluation, float]], reco: Recommandation
) -> None:
    from app.config import settings

    print(
        f"Questions couvertes : {reco.nb_couvertes} ; hors corpus : {reco.nb_hors_corpus}"
    )
    for attendu in ("couvert", "hors_corpus"):
        scores = sorted(s for q, s in resultats if q.attendu == attendu)
        if scores:
            mediane = scores[len(scores) // 2]
            print(
                f"  {attendu:<12} min {scores[0]:.3f}  médiane {mediane:.3f}  max {scores[-1]:.3f}"
            )
    print(f"Seuil actuel RAG_MIN_SCORE = {settings.rag_min_score}")
    print(
        f"Seuil recommandé : {reco.seuil:.2f} "
        f"(hors corpus acceptées : {reco.taux_faux_positifs:.0%}, "
        f"couvertes servies : {reco.taux_couvertes_servies:.0%})"
    )
    for langue, taux in reco.couvertes_servies_par_langue.items():
        print(f"  couvertes servies [{langue}] : {taux:.0%}")
    manquees = [
        (q, s) for q, s in resultats if q.attendu == "couvert" and s < reco.seuil
    ]
    if manquees:
        print(
            "Questions couvertes non servies à ce seuil (à reformuler ou à couvrir) :"
        )
        for q, s in sorted(manquees, key=lambda r: r[1]):
            print(f"  {s:.3f}  [{q.langue}] {q.question}")


async def _main(args: argparse.Namespace) -> int:
    from app.config import settings
    from app.services.rag_service import rag_service

    if rag_service._is_embedding_mock_mode():
        print(
            f"Clé du fournisseur de vecteurs '{settings.embedding_provider}' absente "
            "ou invalide (GEMINI_API_KEY ou MISTRAL_API_KEY selon EMBEDDING_PROVIDER) : "
            "les vecteurs seraient factices, le calibrage n'aurait aucun sens.",
            file=sys.stderr,
        )
        return 2
    print(
        f"Modèle de vecteurs : {settings.espace_embeddings} — "
        f"collection : {settings.collection_vectorielle}"
    )

    questions = charger_jeu(Path(args.jeu))
    resultats = await mesurer_scores(questions, args.avec_reformulation)
    reco = recommander_seuil(resultats, max_faux_positifs=args.max_faux_positifs)
    _afficher(resultats, reco)

    if args.json:
        rapport: dict[str, Any] = {
            "recommandation": asdict(reco),
            "avec_reformulation": args.avec_reformulation,
            "scores": [{**asdict(q), "score": round(s, 4)} for q, s in resultats],
        }
        Path(args.json).write_text(
            json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Rapport écrit : {args.json}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--jeu", default=str(JEU_PAR_DEFAUT))
    parser.add_argument("--max-faux-positifs", type=float, default=0.05)
    parser.add_argument("--avec-reformulation", action="store_true")
    parser.add_argument("--json", default=None)
    logging.basicConfig(level=logging.WARNING)
    sys.exit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
