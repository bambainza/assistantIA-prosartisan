"""Grille de prix de référence : CRUD back-office et tarification des devis.

Les devis extraits par l'IA ne reçoivent un prix unitaire que s'il provient de
cette grille ; sinon la ligne reste à 0 F et doit être complétée par
l'artisan. Le LLM ne fixe jamais de prix.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prix_reference import PrixReference
from app.schemas.prix_reference import PrixReferenceCreate, PrixReferenceUpdate

# Part minimale des mots de la désignation de référence retrouvés dans la
# ligne du devis pour appliquer le prix.
SEUIL_CORRESPONDANCE = 0.6

_MOTS_VIDES = {
    "les",
    "des",
    "une",
    "pour",
    "dans",
    "sur",
    "avec",
    "par",
    "aux",
    "et",
    "de",
    "du",
    "la",
    "le",
}

# Unités équivalentes ramenées à une forme canonique.
_UNITES_CANONIQUES: dict[str, str] = {
    "u": "unite",
    "un": "unite",
    "unite": "unite",
    "unites": "unite",
    "piece": "unite",
    "pieces": "unite",
    "pce": "unite",
    "sac": "sac",
    "sacs": "sac",
    "m3": "m3",
    "m³": "m3",
    "metre cube": "m3",
    "m2": "m2",
    "m²": "m2",
    "metre carre": "m2",
    "ml": "ml",
    "m": "ml",
    "metre": "ml",
    "metre lineaire": "ml",
    "kg": "kg",
    "tonne": "tonne",
    "t": "tonne",
    "litre": "litre",
    "l": "litre",
    "jour": "jour",
    "jours": "jour",
    "j": "jour",
    "heure": "heure",
    "h": "heure",
    "forfait": "forfait",
    "ff": "forfait",
    "voyage": "voyage",
    "chargement": "voyage",
    "rouleau": "rouleau",
    "couronne": "rouleau",
    "barre": "barre",
    "brouette": "brouette",
}


def _sans_accents(texte: str) -> str:
    return (
        unicodedata.normalize("NFKD", texte.lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def normaliser_unite(unite: str | None) -> str:
    """Forme canonique d'une unité (`sacs` → `sac`, `m³` → `m3`, `u` → `unite`)."""
    brute = " ".join(_sans_accents(unite or "").replace("³", "3").split())
    brute = brute.replace("²", "2").strip(" .")
    if brute in _UNITES_CANONIQUES:
        return _UNITES_CANONIQUES[brute]
    # « barre 4m », « sac de 50 kg » → premier mot significatif.
    premier = brute.split(" ")[0] if brute else ""
    return _UNITES_CANONIQUES.get(premier, brute)


def normaliser_commune(commune: str | None) -> str | None:
    if not commune:
        return None
    valeur = " ".join(_sans_accents(commune).split())
    return valeur or None


def mots_significatifs(texte: str) -> set[str]:
    """Mots-clés d'une désignation : sans accents, ≥ 2 caractères, singulier simple."""
    mots = re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", _sans_accents(texte))
    resultat: set[str] = set()
    for mot in mots:
        mot = mot.replace(",", ".")
        if len(mot) < 2 or mot in _MOTS_VIDES:
            continue
        if len(mot) > 3 and mot[-1] in "sx" and not mot[-2].isdigit():
            mot = mot[:-1]
        resultat.add(mot)
    return resultat


@dataclass(frozen=True)
class PrixApplique:
    """Prix retenu pour une ligne de devis."""

    prix_unitaire: int
    prix_reference_id: int
    date_releve: date
    commune: str | None


def _score(designation_ligne: set[str], prix: PrixReference) -> float:
    """Part des mots de la référence (désignation ou un synonyme) présents dans la ligne."""
    candidats = [prix.designation, *(prix.mots_cles or "").split(",")]
    meilleur = 0.0
    for candidat in candidats:
        mots_ref = mots_significatifs(candidat)
        if not mots_ref:
            continue
        # Les nombres (classe de ciment, section, diamètre, épaisseur)
        # distinguent des articles de prix différents : tous doivent figurer
        # dans la ligne, sinon « CPJ 32.5 » recevrait le prix du « CPJ 42.5 ».
        nombres_ref = {m for m in mots_ref if m[0].isdigit()}
        if not nombres_ref <= designation_ligne:
            continue
        couverture = len(mots_ref & designation_ligne) / len(mots_ref)
        meilleur = max(meilleur, couverture)
    return meilleur


def choisir_prix(
    designation: str,
    unite: str,
    commune: str | None,
    grille: Sequence[PrixReference],
) -> PrixApplique | None:
    """Sélectionne le prix de référence applicable à une ligne, ou `None`.

    Règles : même unité canonique ; correspondance de désignation ≥
    `SEUIL_CORRESPONDANCE` ; prix de la commune du chantier, sinon prix sans
    commune (jamais le prix d'une autre commune) ; à égalité, le meilleur
    score puis le relevé le plus récent.
    """
    mots_ligne = mots_significatifs(designation)
    if not mots_ligne:
        return None
    unite_ligne = normaliser_unite(unite)
    commune_chantier = normaliser_commune(commune)

    retenus: list[tuple[int, float, date, PrixReference]] = []
    for prix in grille:
        if not prix.is_active or normaliser_unite(prix.unite) != unite_ligne:
            continue
        commune_prix = normaliser_commune(prix.commune)
        if commune_prix is not None and commune_prix != commune_chantier:
            continue
        score = _score(mots_ligne, prix)
        if score < SEUIL_CORRESPONDANCE:
            continue
        priorite_commune = 1 if commune_prix is not None else 0
        retenus.append((priorite_commune, score, prix.date_releve, prix))

    if not retenus:
        return None
    _, _, _, meilleur = max(retenus, key=lambda r: (r[0], r[1], r[2]))
    return PrixApplique(
        prix_unitaire=int(meilleur.prix_unitaire),
        prix_reference_id=int(meilleur.id),
        date_releve=meilleur.date_releve,
        commune=meilleur.commune,
    )


class PrixReferenceService:
    """Accès à la grille de prix de référence."""

    async def lister(
        self,
        db: AsyncSession,
        *,
        actifs_seulement: bool = False,
        metier_id: int | None = None,
        recherche: str | None = None,
    ) -> list[PrixReference]:
        stmt = select(PrixReference)
        if actifs_seulement:
            stmt = stmt.where(PrixReference.is_active.is_(True))
        if metier_id is not None:
            stmt = stmt.where(
                or_(
                    PrixReference.metier_id.is_(None),
                    PrixReference.metier_id == metier_id,
                )
            )
        if recherche:
            motif = f"%{recherche.strip()}%"
            stmt = stmt.where(
                or_(
                    PrixReference.designation.ilike(motif),
                    PrixReference.mots_cles.ilike(motif),
                )
            )
        stmt = stmt.order_by(PrixReference.designation, PrixReference.id)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def grille_pour_devis(
        self, db: AsyncSession, metier_id: int | None
    ) -> list[PrixReference]:
        """Prix actifs utilisables pour un devis (métier donné ou transverses)."""
        return await self.lister(db, actifs_seulement=True, metier_id=metier_id)

    async def obtenir(self, db: AsyncSession, prix_id: int) -> PrixReference | None:
        res = await db.execute(select(PrixReference).where(PrixReference.id == prix_id))
        return res.scalar_one_or_none()

    async def creer(
        self, db: AsyncSession, payload: PrixReferenceCreate
    ) -> PrixReference:
        prix = PrixReference(**payload.model_dump())
        db.add(prix)
        await db.flush()
        return prix

    async def modifier(
        self, db: AsyncSession, prix_id: int, payload: PrixReferenceUpdate
    ) -> PrixReference | None:
        prix = await self.obtenir(db, prix_id)
        if prix is None:
            return None
        for champ, valeur in payload.model_dump(exclude_unset=True).items():
            setattr(prix, champ, valeur)
        return prix

    async def supprimer(self, db: AsyncSession, prix_id: int) -> PrixReference | None:
        prix = await self.obtenir(db, prix_id)
        if prix is None:
            return None
        await db.delete(prix)
        return prix


prix_reference_service = PrixReferenceService()
