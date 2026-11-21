"""Outillage de calibrage de RAG_MIN_SCORE (sans réseau)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.scripts.calibrer_seuil_rag import (
    JEU_PAR_DEFAUT,
    QuestionEvaluation,
    charger_jeu,
    recommander_seuil,
)


def _q(attendu: str, langue: str = "fr") -> QuestionEvaluation:
    return QuestionEvaluation(question="q", attendu=attendu, langue=langue)


def test_seuil_le_plus_bas_sous_le_plafond_de_faux_positifs() -> None:
    resultats = [
        (_q("couvert"), 0.82),
        (_q("couvert"), 0.78),
        (_q("couvert", "nouchi"), 0.70),
        (_q("couvert", "nouchi"), 0.66),
        (_q("hors_corpus"), 0.71),
        (_q("hors_corpus"), 0.64),
        (_q("hors_corpus"), 0.60),
        (_q("hors_corpus"), 0.55),
    ]
    reco = recommander_seuil(resultats, max_faux_positifs=0.0)
    assert reco.seuil == pytest.approx(0.72)
    assert reco.taux_faux_positifs == 0
    assert reco.taux_couvertes_servies == 0.5
    assert reco.couvertes_servies_par_langue == {"fr": 1.0, "nouchi": 0.0}

    tolerant = recommander_seuil(resultats, max_faux_positifs=0.25)
    assert tolerant.seuil == pytest.approx(0.65)
    assert tolerant.taux_couvertes_servies == 1.0


def test_jeu_incomplet_refuse() -> None:
    with pytest.raises(ValueError, match="couvertes et hors corpus"):
        recommander_seuil([(_q("couvert"), 0.9)])


def test_jeu_fourni_valide_et_equilibre() -> None:
    questions = charger_jeu(JEU_PAR_DEFAUT)
    couvertes = [q for q in questions if q.attendu == "couvert"]
    hors = [q for q in questions if q.attendu == "hors_corpus"]
    assert len(couvertes) >= 45 and len(hors) >= 45
    assert any(q.langue != "fr" for q in couvertes)
    documents = Path(JEU_PAR_DEFAUT).parents[1] / "documents"
    for q in couvertes:
        assert q.document and (documents / q.document).is_file(), q.question


def test_ligne_invalide_signalee(tmp_path: Path) -> None:
    jeu = tmp_path / "jeu.jsonl"
    jeu.write_text('{"question": "x", "attendu": "peut-etre"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="jeu.jsonl:1"):
        charger_jeu(jeu)
