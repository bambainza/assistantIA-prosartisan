"""
Service de gestion des devis et factures pro-forma pour artisans.

Gère l'extraction automatique par IA depuis transcription vocale,
le calcul mathématique rigoureux des montants (HT/TTC/Acomptes),
la génération de messages WhatsApp prêts à l'envoi et les documents HTML/PDF.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from mistralai.client import Mistral
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.quote import Quote
from app.models.user import User
from app.schemas.prix_reference import TYPES_ITEM
from app.schemas.quote import (
    PRIX_A_SAISIR,
    PRIX_ARTISAN,
    PRIX_GRILLE,
    QuoteExtractResponse,
    QuoteItem,
)
from app.services.calculator_service import calculator_service
from app.services.llm_provider_service import (
    FournisseursIAIndisponiblesError,
    llm_provider_service,
)
from app.services.prix_reference_service import choisir_prix, prix_reference_service

logger = logging.getLogger(__name__)

# Calculateurs dont le résultat se traduit en lignes de fournitures.
CALCULS_DEVIS: frozenset[str] = frozenset(
    {
        "calculer_dosage_beton",
        "calculer_materiaux_btp",
        "calculer_agglos_mur",
        "calculer_carrelage_et_colle",
    }
)

EXTRACTION_PROMPT = (
    "Tu es l'assistant de préparation de devis de ProsArtisan pour les artisans "
    "de Côte d'Ivoire. À partir de la description des travaux (français ou "
    "nouchi de chantier), tu extrais un titre, le client s'il est mentionné, la "
    "commune du chantier, et les lignes du devis.\n"
    "RÈGLES STRICTES :\n"
    "1. N'invente JAMAIS de prix : les prix viennent de la grille de référence "
    "de ProsArtisan. Seule exception : si l'artisan a lui-même écrit le prix "
    "unitaire d'une ligne dans sa description, recopie ce nombre exact dans "
    '"prix_cite" ; sinon "prix_cite" vaut null.\n'
    "2. Quand la description donne des dimensions de béton, de mortier, de mur "
    "en agglos ou de carrelage, n'énumère pas ces matériaux toi-même : ajoute un "
    'calcul dans "calculs" avec les dimensions données. Outils autorisés :\n'
    "   - calculer_dosage_beton : volume_m3 OU longueur_m, largeur_m, "
    "epaisseur_m ; type_ouvrage parmi beton_proprete, fondation_semelle, "
    "poteau_poutre_dalle, mortier_pose_parpaing, mortier_enduit_chape ; "
    'classe_ciment "CPJ 42.5" ou "CPJ 32.5".\n'
    "   - calculer_agglos_mur : longueur_m, hauteur_m, surface_ouvertures_m2, "
    "epaisseur_agglo_cm (10, 15 ou 20).\n"
    "   - calculer_carrelage_et_colle : surface_m2, format_carreau_cm, type_pose "
    "(droite, diagonale, chevron).\n"
    "   N'invente aucune dimension : sans dimension, pas de calcul.\n"
    '3. Les autres fournitures et la main d\'œuvre vont dans "items", avec la '
    "quantité indiquée par l'artisan (1 si elle n'est pas précisée).\n"
    "4. type_item vaut FOURNITURE, MAIN_D_OEUVRE ou FORFAIT.\n"
    "Réponds UNIQUEMENT par un objet JSON strict de cette forme :\n"
    "{\n"
    '  "titre": "Titre des travaux",\n'
    '  "client_nom": "Nom du client ou Client Particulier",\n'
    '  "client_telephone": null,\n'
    '  "client_adresse": "Commune du chantier ou null",\n'
    '  "delai_estime_jours": 3,\n'
    '  "items": [\n'
    '     {"description": "Disjoncteur divisionnaire 20A", "quantite": 3, "unite": "unité", "type_item": "FOURNITURE", "prix_cite": null},\n'
    '     {"description": "Pose et raccordement", "quantite": 1, "unite": "forfait", "type_item": "MAIN_D_OEUVRE", "prix_cite": 25000}\n'
    "  ],\n"
    '  "calculs": [\n'
    '     {"outil": "calculer_agglos_mur", "arguments": {"longueur_m": 10, "hauteur_m": 2.5, "epaisseur_agglo_cm": 15}}\n'
    "  ],\n"
    '  "recommandations": []\n'
    "}"
)


class DevisIndisponibleError(RuntimeError):
    """L'analyse IA du devis est impossible : la route répond 503.

    Jamais de devis factice à la place (prix inventés présentés comme réels).
    """


class QuoteService:
    """Service métier de facturation et devis pro-forma."""

    def __init__(self) -> None:
        self.mistral_client = Mistral(api_key=settings.mistral_api_key)

    @staticmethod
    def calculate_totals(
        items: list[QuoteItem] | list[dict[str, Any]],
        remise_pct: float = 0.0,
        tva_pct: float = 0.0,
        acompte_pct: float = 30.0,
    ) -> dict[str, Any]:
        """Calcule avec précision les totaux de lignes, total HT, remises, TVA et acompte."""
        total_ht = 0
        computed_items: list[dict[str, Any]] = []

        for item in items:
            data = item.model_dump() if isinstance(item, QuoteItem) else dict(item)
            qty = float(data.get("quantite", 1.0))
            pu = int(data.get("prix_unitaire", 0))
            line_total = round(qty * pu)
            total_ht += line_total

            computed = {
                "description": str(data.get("description", "")),
                "quantite": qty,
                "unite": str(data.get("unite", "unité")),
                "prix_unitaire": pu,
                "total": line_total,
                "type_item": str(data.get("type_item", "FOURNITURE")),
            }
            # Traçabilité de l'origine du prix et de la quantité, si connue.
            for cle in ("prix_source", "prix_reference_id", "quantite_source"):
                if data.get(cle) is not None:
                    computed[cle] = data[cle]
            computed_items.append(computed)

        # Application de la remise commerciale
        montant_remise = round(total_ht * (remise_pct / 100.0))
        total_apres_remise = max(0, total_ht - montant_remise)

        # Application de la TVA
        montant_tva = round(total_apres_remise * (tva_pct / 100.0))
        total_ttc = total_apres_remise + montant_tva

        # Acompte
        montant_acompte = round(total_ttc * (acompte_pct / 100.0))
        solde_restant = max(0, total_ttc - montant_acompte)

        return {
            "items": computed_items,
            "total_ht": total_ht,
            "montant_remise": montant_remise,
            "remise_pct": remise_pct,
            "montant_tva": montant_tva,
            "tva_pct": tva_pct,
            "total_ttc": total_ttc,
            "acompte_pct": acompte_pct,
            "montant_acompte": montant_acompte,
            "solde_restant": solde_restant,
        }

    async def generate_next_number(self, db: AsyncSession) -> str:
        """Génère un numéro unique chronologique DEV-YYYYMM-XXXX."""
        now = datetime.now(UTC)
        prefix = f"DEV-{now.strftime('%Y%m')}-"

        stmt = select(func.count(Quote.id)).where(Quote.numero.like(f"{prefix}%"))
        res = await db.execute(stmt)
        count = (res.scalar() or 0) + 1
        return f"{prefix}{count:04d}"

    async def extract_quote_from_text(
        self,
        description_brute: str,
        client_nom: str | None = None,
        client_telephone: str | None = None,
        metier_id: int | None = None,
        commune: str | None = None,
        db: AsyncSession | None = None,
    ) -> QuoteExtractResponse:
        """Pré-remplit un devis depuis une note vocale ou écrite de l'artisan.

        Le LLM n'extrait que les désignations, les quantités et, quand des
        dimensions sont données, les calculs à confier aux calculateurs
        certifiés. Les prix viennent exclusivement de la grille de référence
        (`prix_references`) ; à défaut, la ligne reste à 0 F, à compléter par
        l'artisan. Si aucun fournisseur IA ne répond, lève
        `DevisIndisponibleError` (503) : jamais de devis factice.
        """
        mode_demonstration = False
        if not llm_provider_service.is_any_provider_configured():
            if settings.is_production:
                # Inaccessible si le contrôle de démarrage est respecté.
                raise DevisIndisponibleError(
                    "Aucun fournisseur IA n'est configuré pour l'analyse des devis."
                )
            brut = self._mock_extraction(description_brute)
            mode_demonstration = True
        else:
            messages = [
                {"role": "system", "content": EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"Description des travaux de l'artisan : {description_brute}",
                },
            ]
            try:
                raw_text = await llm_provider_service.complete_text_with_failover(
                    messages=messages,
                    mistral_client=self.mistral_client,
                    temperature=0.1,
                )
            except FournisseursIAIndisponiblesError as exc:
                raise DevisIndisponibleError(
                    "Analyse IA du devis momentanément indisponible."
                ) from exc
            brut = self._parse_llm_json(raw_text)

        grille = (
            await prix_reference_service.grille_pour_devis(db, metier_id)
            if db is not None
            else []
        )
        return self._construire_proposition(
            brut,
            description_brute=description_brute,
            grille=grille,
            client_nom=client_nom,
            client_telephone=client_telephone,
            commune=commune,
            mode_demonstration=mode_demonstration,
        )

    @staticmethod
    def _parse_llm_json(raw_text: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw_text or "").strip())
        try:
            data = json.loads(cleaned)
        except (TypeError, ValueError) as exc:
            logger.warning("Réponse IA du devis non exploitable : %s", exc)
            raise DevisIndisponibleError(
                "La réponse de l'IA n'a pas pu être interprétée."
            ) from exc
        if not isinstance(data, dict):
            raise DevisIndisponibleError(
                "La réponse de l'IA n'a pas pu être interprétée."
            )
        return data

    @staticmethod
    def _prix_cite_verifie(valeur: Any, description: str) -> int | None:
        """Prix recopié par l'IA, accepté seulement s'il figure dans la description.

        Les séparateurs de milliers (espace, point, espace insécable) sont
        ignorés : « 75 000 F » ou « 75.000 » valident un prix de 75000.
        """
        if valeur is None or isinstance(valeur, bool):
            return None
        try:
            nombre = float(valeur)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(nombre) or nombre <= 0 or nombre != int(nombre):
            return None
        prix = int(nombre)
        compact = re.sub(r"(?<=\d)[\s.  ](?=\d{3}(?!\d))", "", description)
        return prix if str(prix) in re.findall(r"\d+", compact) else None

    @staticmethod
    def _quantite_valide(valeur: Any) -> float | None:
        try:
            quantite = float(valeur)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(quantite) or quantite <= 0:
            return None
        return round(quantite, 3)

    @classmethod
    def _lignes_depuis_calcul(
        cls, outil: str, arguments: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Exécute un calculateur certifié et traduit son résultat en lignes de devis."""
        resultat = calculator_service.execute_tool(outil, arguments)
        res = resultat.get("resultats", {})
        lignes: list[tuple[str, Any, str]] = []

        if outil in {"calculer_dosage_beton", "calculer_materiaux_btp"}:
            lignes = [
                (
                    f"Ciment {resultat.get('classe_ciment', 'CPJ 42.5')} (sac de 50 kg)",
                    res.get("sacs_ciment_50kg"),
                    "sac",
                ),
                ("Sable", res.get("sable_m3"), "m3"),
                ("Gravier", res.get("gravier_m3"), "m3"),
            ]
        elif outil == "calculer_agglos_mur":
            lignes = [
                (
                    f"Agglo creux {resultat.get('epaisseur_agglo_cm', 15)} cm (40x20)",
                    res.get("agglos_unites"),
                    "unite",
                ),
                ("Ciment CPJ 42.5 (sac de 50 kg)", res.get("sacs_ciment_50kg"), "sac"),
                ("Sable", res.get("sable_m3"), "m3"),
            ]
        elif outil == "calculer_carrelage_et_colle":
            colle = resultat.get("mortier_colle", {})
            joint = resultat.get("mortier_joint", {})
            lignes = [
                (
                    f"Carreaux {arguments.get('format_carreau_cm', '')}".strip(),
                    resultat.get("surface_a_commander_m2"),
                    "m2",
                ),
                ("Mortier colle (sac de 25 kg)", colle.get("sacs_25kg"), "sac"),
                ("Joint carrelage (sac de 5 kg)", joint.get("sacs_5kg"), "sac"),
            ]

        return [
            {
                "description": designation,
                "quantite": quantite,
                "unite": unite,
                "type_item": "FOURNITURE",
                "quantite_source": "calculateur",
            }
            for designation, valeur, unite in lignes
            if (quantite := cls._quantite_valide(valeur)) is not None
        ]

    def _construire_proposition(
        self,
        brut: dict[str, Any],
        *,
        description_brute: str,
        grille: list[Any],
        client_nom: str | None,
        client_telephone: str | None,
        commune: str | None,
        mode_demonstration: bool,
    ) -> QuoteExtractResponse:
        avertissements: list[str] = []
        lignes: list[dict[str, Any]] = []

        # 1. Lignes calculées par les calculateurs certifiés (quantités sûres).
        calculees: dict[tuple[str, str], dict[str, Any]] = {}
        for calcul in brut.get("calculs") or []:
            if not isinstance(calcul, dict):
                continue
            outil = str(calcul.get("outil", ""))
            arguments = calcul.get("arguments") or {}
            if outil not in CALCULS_DEVIS or not isinstance(arguments, dict):
                avertissements.append(
                    f"Calcul « {outil or '?'} » ignoré : outil non pris en charge pour un devis."
                )
                continue
            try:
                for ligne in self._lignes_depuis_calcul(outil, arguments):
                    cle = (ligne["description"].lower(), ligne["unite"])
                    if cle in calculees:
                        calculees[cle]["quantite"] = round(
                            calculees[cle]["quantite"] + ligne["quantite"], 3
                        )
                    else:
                        calculees[cle] = ligne
            except ValueError as exc:
                avertissements.append(f"Calcul « {outil} » impossible : {exc}")
        lignes.extend(calculees.values())

        # 2. Lignes énumérées par l'IA (quantités à vérifier par l'artisan).
        lignes_ignorees = 0
        for it in brut.get("items") or []:
            if not isinstance(it, dict):
                continue
            description = str(it.get("description") or "").strip()[:200]
            quantite = self._quantite_valide(it.get("quantite", 1.0))
            if not description or quantite is None:
                lignes_ignorees += 1
                continue
            type_item = str(it.get("type_item") or "FOURNITURE").strip().upper()
            lignes.append(
                {
                    "description": description,
                    "quantite": quantite,
                    "unite": str(it.get("unite") or "unité").strip()[:30] or "unité",
                    "type_item": type_item if type_item in TYPES_ITEM else "FOURNITURE",
                    "quantite_source": "ia",
                    "prix_cite": self._prix_cite_verifie(
                        it.get("prix_cite"), description_brute
                    ),
                }
            )
        if lignes_ignorees:
            avertissements.append(
                f"{lignes_ignorees} ligne(s) proposée(s) par l'IA ignorée(s) : désignation ou quantité invalide."
            )

        # 3. Prix : dicté par l'artisan (vérifié), sinon grille de référence,
        #    sinon à saisir. Jamais un prix proposé par l'IA.
        commune_chantier = commune or brut.get("client_adresse")
        items: list[QuoteItem] = []
        sans_prix = 0
        for ligne in lignes:
            prix = choisir_prix(
                ligne["description"], ligne["unite"], commune_chantier, grille
            )
            if ligne.get("prix_cite") is not None:
                prix_unitaire, source, ref_id = ligne["prix_cite"], PRIX_ARTISAN, None
            elif prix is None:
                sans_prix += 1
                prix_unitaire, source, ref_id = 0, PRIX_A_SAISIR, None
            else:
                prix_unitaire, source, ref_id = (
                    prix.prix_unitaire,
                    PRIX_GRILLE,
                    prix.prix_reference_id,
                )
            items.append(
                QuoteItem(
                    description=ligne["description"],
                    quantite=ligne["quantite"],
                    unite=ligne["unite"],
                    prix_unitaire=prix_unitaire,
                    total=round(ligne["quantite"] * prix_unitaire),
                    type_item=ligne["type_item"],
                    prix_source=source,
                    prix_reference_id=ref_id,
                    quantite_source=ligne["quantite_source"],
                )
            )

        if sans_prix:
            avertissements.append(
                f"{sans_prix} ligne(s) sans prix de référence : prix à saisir par l'artisan."
            )
        if any(it.quantite_source == "ia" for it in items):
            avertissements.append(
                "Les quantités proposées par l'IA sont à vérifier avant envoi au client."
            )
        if mode_demonstration:
            avertissements.insert(
                0,
                "Mode démonstration : aucune IA n'est configurée, les lignes sont des exemples génériques.",
            )

        recommandations = [
            str(r).strip()[:300]
            for r in (brut.get("recommandations") or [])
            if isinstance(r, str) and r.strip()
        ][:5]

        try:
            delai = int(brut.get("delai_estime_jours") or 0) or None
        except (TypeError, ValueError):
            delai = None

        return QuoteExtractResponse(
            titre=str(brut.get("titre") or "Travaux d'artisanat")[:200],
            client_nom=client_nom
            or str(brut.get("client_nom") or "Client Particulier")[:150],
            client_telephone=client_telephone or brut.get("client_telephone"),
            client_adresse=brut.get("client_adresse"),
            items=items,
            delai_estime_jours=delai if delai and delai > 0 else None,
            recommandations=recommandations,
            lignes_sans_prix=sans_prix,
            mode_demonstration=mode_demonstration,
            avertissements=avertissements,
        )

    @staticmethod
    def _mock_extraction(description_brute: str) -> dict[str, Any]:
        """Extraction de démonstration (dev/tests sans clé IA), sans aucun prix.

        Mêmes champs que la réponse attendue du LLM ; les prix sont ensuite
        cherchés dans la grille comme en mode réel.
        """
        desc_lower = description_brute.lower()

        if any(m in desc_lower for m in ("disjoncteur", "câble", "prise", "courant")):
            titre = "Travaux d'installation et mise en sécurité électrique"
            items = [
                ("Disjoncteur divisionnaire 20A", 3.0, "unité", "FOURNITURE"),
                ("Câble cuivre rigide 2.5 mm²", 40.0, "ml", "FOURNITURE"),
                ("Prise de courant 2P+T encastrée", 6.0, "unité", "FOURNITURE"),
                (
                    "Main d'œuvre tirage de lignes et raccordement tableau",
                    1.0,
                    "forfait",
                    "MAIN_D_OEUVRE",
                ),
            ]
        elif any(
            m in desc_lower for m in ("ciment", "béton", "mur", "parpaing", "poteau")
        ):
            titre = "Travaux de maçonnerie et coulage béton"
            items = [
                ("Ciment CPJ 42.5 (sac de 50 kg)", 10.0, "sac", "FOURNITURE"),
                ("Sable de lagune", 1.0, "m3", "FOURNITURE"),
                ("Main d'œuvre maçonnerie et coffrage", 3.0, "jour", "MAIN_D_OEUVRE"),
            ]
        elif any(
            m in desc_lower for m in ("tuyau", "fuite", "wc", "douche", "robinet")
        ):
            titre = "Travaux de plomberie sanitaire et évacuation"
            items = [
                ("Tube PVC évacuation DN 100", 2.0, "barre", "FOURNITURE"),
                ("Robinet d'arrêt laiton 1/2", 2.0, "unité", "FOURNITURE"),
                ("Main d'œuvre plomberie", 1.0, "forfait", "MAIN_D_OEUVRE"),
            ]
        else:
            titre = "Prestations de travaux et fournitures"
            items = [
                ("Fournitures de chantier", 1.0, "forfait", "FOURNITURE"),
                ("Main d'œuvre d'exécution", 1.0, "forfait", "MAIN_D_OEUVRE"),
            ]

        return {
            "titre": titre,
            "client_nom": "Client Particulier",
            "client_adresse": None,
            "delai_estime_jours": 3,
            "items": [
                {"description": d, "quantite": q, "unite": u, "type_item": t}
                for d, q, u, t in items
            ],
            "calculs": [],
            "recommandations": [],
        }

    @staticmethod
    def generate_whatsapp_text(
        quote: Quote,
        artisan_nom: str = "Artisan Professionnel",
        artisan_phone: str = "",
    ) -> str:
        """Génère un récapitulatif textuel optimisé pour partage WhatsApp."""
        lines = [
            "👷‍♂️ *PROSARTISAN — DEVIS PRO-FORMA*",
            f"📄 *N° :* {quote.numero}",
            f"🎯 *Objet :* {quote.titre}",
            f"👤 *Client :* {quote.client_nom}",
            "",
            "📋 *DÉTAIL DES POSTES :*",
        ]

        for it in quote.items:
            qty_str = (
                f"{it['quantite']:.0f}"
                if it["quantite"] == int(it["quantite"])
                else f"{it['quantite']}"
            )
            lines.append(
                f"• {qty_str} {it['unite']} x {it['description']} : *{it['total']:,} F CFA*".replace(
                    ",", " "
                )
            )

        lines.extend(
            [
                "",
                f"💵 *TOTAL HT :* {quote.total_ht:,} F CFA".replace(",", " "),
            ]
        )

        if quote.remise_pct > 0:
            lines.append(
                f"🏷️ *Remise ({quote.remise_pct:.0f}%) :* -{round(quote.total_ht * quote.remise_pct / 100):,} F CFA".replace(
                    ",", " "
                )
            )

        lines.extend(
            [
                f"💰 *TOTAL NET À PAYER :* *{quote.total_ttc:,} F CFA*".replace(
                    ",", " "
                ),
                f"💳 *Acompte au démarrage ({quote.acompte_demande_pct:.0f}%) :* *{quote.montant_acompte:,} F CFA*".replace(
                    ",", " "
                ),
                f"⏳ *Délai d'exécution :* {quote.delai_jours or 3} jours ouvrés",
                f"📍 *Règlement :* {quote.mode_paiement}",
            ]
        )

        if artisan_phone:
            lines.append(f"📲 *Contact Artisan :* {artisan_phone} ({artisan_nom})")

        lines.extend(
            [
                "",
                "👉 _Veuillez confirmer votre accord en répondant à ce message._",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def generate_quote_html(quote: Quote, artisan: User | None = None) -> str:
        """Génère un document HTML prêt pour l'impression ou la conversion PDF."""
        artisan_name = (
            artisan.nom
            if artisan and hasattr(artisan, "nom") and artisan.nom
            else "ProsArtisan Expert"
        )
        artisan_tel = (
            artisan.telephone
            if artisan and hasattr(artisan, "telephone") and artisan.telephone
            else "Contact non renseigné"
        )

        rows_html = ""
        for i, it in enumerate(quote.items, 1):
            qty_str = (
                f"{it['quantite']:.0f}"
                if it["quantite"] == int(it["quantite"])
                else f"{it['quantite']}"
            )
            rows_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: center;">{i}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb;">
                    <strong>{it["description"]}</strong>
                    <span style="display: block; font-size: 11px; color: #6b7280;">{it.get("type_item", "FOURNITURE")}</span>
                </td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: center;">{qty_str} {it["unite"]}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: right;">{it["prix_unitaire"]:,} F</td>
                <td style="padding: 10px; border-bottom: 1px solid #e5e7eb; text-align: right; font-weight: bold;">{it["total"]:,} F</td>
            </tr>
            """.replace(",", " ")

        date_str = quote.date_emission.strftime("%d/%m/%Y")
        validite_str = (quote.date_emission + timedelta(days=30)).strftime("%d/%m/%Y")

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Devis {quote.numero} — {quote.titre}</title>
    <style>
        body {{ font-family: 'Segoe UI', Helvetica, Arial, sans-serif; margin: 0; padding: 30px; color: #1f2937; background: #fff; line-height: 1.5; }}
        .header {{ display: flex; justify-content: space-between; border-bottom: 3px solid #10b981; padding-bottom: 20px; margin-bottom: 25px; }}
        .logo {{ font-size: 24px; font-weight: bold; color: #10b981; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; background: #ecfdf5; color: #059669; border: 1px solid #a7f3d0; }}
        .info-grid {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
        .info-box {{ width: 48%; background: #f9fafb; padding: 15px; border-radius: 6px; border: 1px solid #f3f4f6; }}
        .info-box h3 {{ margin-top: 0; margin-bottom: 8px; font-size: 14px; color: #4b5563; text-transform: uppercase; letter-spacing: 0.5px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 13px; }}
        th {{ background: #111827; color: #fff; padding: 10px; text-align: left; }}
        .totals-table {{ width: 340px; margin-left: auto; margin-bottom: 30px; font-size: 13px; }}
        .totals-table td {{ padding: 6px 12px; }}
        .totals-table tr.total-row td {{ font-size: 16px; font-weight: bold; color: #10b981; border-top: 2px solid #10b981; padding-top: 10px; }}
        .footer-terms {{ background: #f9fafb; padding: 15px; border-radius: 6px; border-left: 4px solid #10b981; font-size: 12px; margin-bottom: 30px; }}
        .signature-grid {{ display: flex; justify-content: space-between; margin-top: 40px; }}
        .sign-box {{ width: 45%; height: 90px; border: 1px dashed #9ca3af; border-radius: 6px; padding: 10px; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="logo">👷‍♂️ ProsArtisan</div>
            <div style="font-size: 13px; color: #4b5563; margin-top: 4px;">Copilote technique & devis certifié</div>
        </div>
        <div style="text-align: right;">
            <span class="badge">DEVIS PRO-FORMA</span>
            <h2 style="margin: 6px 0 2px 0; font-size: 20px;">N° {quote.numero}</h2>
            <div style="font-size: 12px; color: #6b7280;">Date : {date_str} | Validité : {validite_str}</div>
        </div>
    </div>

    <div class="info-grid">
        <div class="info-box">
            <h3>Émetteur (Artisan)</h3>
            <div style="font-size: 14px; font-weight: bold;">{artisan_name}</div>
            <div style="font-size: 13px; color: #4b5563; margin-top: 4px;">📲 {artisan_tel}</div>
            <div style="font-size: 12px; color: #6b7280; margin-top: 2px;">Réseau certifié ProsArtisan Côte d'Ivoire</div>
        </div>
        <div class="info-box">
            <h3>Destinataire (Client)</h3>
            <div style="font-size: 14px; font-weight: bold;">{quote.client_nom}</div>
            <div style="font-size: 13px; color: #4b5563; margin-top: 4px;">📞 {quote.client_telephone or "Non renseigné"}</div>
            <div style="font-size: 12px; color: #6b7280; margin-top: 2px;">📍 {quote.client_adresse or "Abidjan"}</div>
        </div>
    </div>

    <div style="margin-bottom: 15px;">
        <strong style="font-size: 15px; color: #111827;">Objet : {quote.titre}</strong>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 5%; text-align: center;">#</th>
                <th style="width: 50%;">Désignation des Prestations & Fournitures</th>
                <th style="width: 15%; text-align: center;">Qté</th>
                <th style="width: 15%; text-align: right;">Prix Unitaire</th>
                <th style="width: 15%; text-align: right;">Total Net</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <table class="totals-table">
        <tr>
            <td>Total Brut HT :</td>
            <td style="text-align: right; font-weight: bold;">{quote.total_ht:,} F CFA</td>
        </tr>
        <tr>
            <td>Remise commerciale ({quote.remise_pct:.0f}%) :</td>
            <td style="text-align: right; color: #dc2626;">-{round(quote.total_ht * quote.remise_pct / 100):,} F CFA</td>
        </tr>
        <tr class="total-row">
            <td>NET À PAYER :</td>
            <td style="text-align: right;">{quote.total_ttc:,} F CFA</td>
        </tr>
        <tr>
            <td style="font-size: 12px; color: #4b5563;">Acompte démarrage ({quote.acompte_demande_pct:.0f}%) :</td>
            <td style="text-align: right; font-weight: bold; color: #059669;">{quote.montant_acompte:,} F CFA</td>
        </tr>
        <tr>
            <td style="font-size: 12px; color: #4b5563;">Solde à la réception :</td>
            <td style="text-align: right;">{quote.total_ttc - quote.montant_acompte:,} F CFA</td>
        </tr>
    </table>

    <div class="footer-terms">
        <strong>Conditions & Modalités de Réalisation :</strong><br>
        • Mode de règlement accepté : <strong>{quote.mode_paiement}</strong><br>
        • Délai estimatif des travaux : <strong>{quote.delai_jours or 3} jours ouvrés</strong> à compter de la réception de l'acompte.<br>
        • Tout travail supplémentaire non mentionné au présent devis fera l'objet d'un avenant validé au préalable.
    </div>

    <div class="signature-grid">
        <div class="sign-box">
            <strong>Signature et Cachet de l'Artisan</strong>
        </div>
        <div class="sign-box">
            <strong>Bon pour Accord (Date & Signature Client)</strong>
            <div style="font-size: 10px; margin-top: 30px;">Mention manuscrite "Bon pour accord"</div>
        </div>
    </div>
</body>
</html>""".replace(",", " ")


quote_service = QuoteService()
