"""
Service de gestion des devis et factures pro-forma pour artisans.

Gère l'extraction automatique par IA depuis transcription vocale,
le calcul mathématique rigoureux des montants (HT/TTC/Acomptes),
la génération de messages WhatsApp prêts à l'envoi et les documents HTML/PDF.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from mistralai.client import Mistral
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.quote import Quote
from app.models.user import User
from app.schemas.quote import QuoteExtractResponse, QuoteItem

logger = logging.getLogger(__name__)


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
            if isinstance(item, QuoteItem):
                desc = item.description
                qty = float(item.quantite)
                unit = item.unite
                pu = int(item.prix_unitaire)
                t_item = item.type_item
            else:
                desc = str(item.get("description", ""))
                qty = float(item.get("quantite", 1.0))
                unit = str(item.get("unite", "unité"))
                pu = int(item.get("prix_unitaire", 0))
                t_item = str(item.get("type_item", "FOURNITURE"))

            line_total = round(qty * pu)
            total_ht += line_total

            computed_items.append(
                {
                    "description": desc,
                    "quantite": qty,
                    "unite": unit,
                    "prix_unitaire": pu,
                    "total": line_total,
                    "type_item": t_item,
                }
            )

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
    ) -> QuoteExtractResponse:
        """Extrait les lignes de devis et tarifs indicatifs depuis une note vocale ou écrite."""
        if (
            settings.mistral_api_key.startswith("sk-placeholder")
            or settings.mistral_api_key == "sk-placeholder"
        ):
            # Mode Mock déterministe pour tests locaux
            return self._mock_extract(
                description_brute=description_brute,
                client_nom=client_nom,
                client_telephone=client_telephone,
            )

        system_prompt = (
            "Tu es l'assistant de chiffrage et devis pour artisans de ProsArtisan en Côte d'Ivoire. "
            "À partir de la description des travaux fournie par l'artisan (en français ou en nouchi de chantier), "
            "tu dois extraire un titre clair, identifier le client si mentionné, et découper les travaux "
            "en lignes de devis réalistes avec fournitures et main d'œuvre aux prix du marché d'Abidjan en F CFA (XOF).\n"
            "Réponds UNIQUEMENT sous forme d'un objet JSON strict respectant ce schéma :\n"
            "{\n"
            '  "titre": "Titre des travaux",\n'
            '  "client_nom": "Nom du client ou Client Particulier",\n'
            '  "client_telephone": "Téléphone si mentionné ou null",\n'
            '  "client_adresse": "Commune/lieu si mentionné ou null",\n'
            '  "delai_estime_jours": 3,\n'
            '  "items": [\n'
            '     {"description": "Désignation", "quantite": 2, "unite": "sac", "prix_unitaire": 5000, "type_item": "FOURNITURE"},\n'
            '     {"description": "Pose et raccordement", "quantite": 1, "unite": "forfait", "prix_unitaire": 25000, "type_item": "MAIN_D_OEUVRE"}\n'
            "  ],\n"
            '  "recommandations": ["Avertissement technique ou conseil sécurité"]\n'
            "}"
        )

        try:
            completion = await self.mistral_client.chat.complete_async(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Description des travaux de l'artisan : {description_brute}",
                    },
                ],
                temperature=0.1,
            )
            raw_text = completion.choices[0].message.content or "{}"
            # Nettoyer d'éventuels backticks markdown
            cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip())
            data = json.loads(cleaned_json)

            items = [
                QuoteItem(
                    description=it.get("description", "Prestation"),
                    quantite=float(it.get("quantite", 1.0)),
                    unite=str(it.get("unite", "unité")),
                    prix_unitaire=int(it.get("prix_unitaire", 0)),
                    total=int(
                        float(it.get("quantite", 1.0)) * int(it.get("prix_unitaire", 0))
                    ),
                    type_item=str(it.get("type_item", "FOURNITURE")),
                )
                for it in data.get("items", [])
            ]

            return QuoteExtractResponse(
                titre=data.get("titre", "Travaux d'artisanat"),
                client_nom=client_nom or data.get("client_nom", "Client Particulier"),
                client_telephone=client_telephone or data.get("client_telephone"),
                client_adresse=data.get("client_adresse"),
                items=items,
                delai_estime_jours=data.get("delai_estime_jours", 2),
                recommandations=data.get("recommandations", []),
            )
        except Exception as err:
            logger.warning("Erreur extraction LLM devis : %s -> fallback mock", err)
            return self._mock_extract(
                description_brute=description_brute,
                client_nom=client_nom,
                client_telephone=client_telephone,
            )

    @staticmethod
    def _mock_extract(
        description_brute: str,
        client_nom: str | None = None,
        client_telephone: str | None = None,
    ) -> QuoteExtractResponse:
        """Fallback déterministe pour tests locaux et mode hors-ligne."""
        items: list[QuoteItem] = []
        desc_lower = description_brute.lower()

        # Électricité
        if (
            "disjoncteur" in desc_lower
            or "câble" in desc_lower
            or "prise" in desc_lower
            or "courant" in desc_lower
        ):
            titre = "Travaux d'installation et mise en sécurité électrique"
            items.append(
                QuoteItem(
                    description="Disjoncteurs divisionnaires 16A/20A",
                    quantite=3.0,
                    unite="unité",
                    prix_unitaire=6000,
                    total=18000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Câble cuivre rigide 2.5 mm² (couronne 50m)",
                    quantite=1.0,
                    unite="rouleau",
                    prix_unitaire=28000,
                    total=28000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Prises de courant 2P+T encastrées",
                    quantite=6.0,
                    unite="unité",
                    prix_unitaire=2500,
                    total=15000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Main d'œuvre, tirage de lignes et raccordement tableau",
                    quantite=1.0,
                    unite="forfait",
                    prix_unitaire=35000,
                    total=35000,
                    type_item="MAIN_D_OEUVRE",
                )
            )
        # Maçonnerie
        elif (
            "ciment" in desc_lower
            or "béton" in desc_lower
            or "mur" in desc_lower
            or "parpaing" in desc_lower
            or "poteau" in desc_lower
        ):
            titre = "Travaux de maçonnerie et coulage béton"
            items.append(
                QuoteItem(
                    description="Ciment CPJ 42.5 (sacs de 50 kg)",
                    quantite=10.0,
                    unite="sac",
                    prix_unitaire=5000,
                    total=50000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Sable de lagune propre (chargement)",
                    quantite=1.0,
                    unite="voyage",
                    prix_unitaire=35000,
                    total=35000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Gravier concassé 15/25",
                    quantite=1.0,
                    unite="voyage",
                    prix_unitaire=45000,
                    total=45000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Main d'œuvre maçonnerie et coffrage",
                    quantite=3.0,
                    unite="jour",
                    prix_unitaire=15000,
                    total=45000,
                    type_item="MAIN_D_OEUVRE",
                )
            )
        # Plomberie / Sanitaire
        elif (
            "tuyau" in desc_lower
            or "fuite" in desc_lower
            or "wc" in desc_lower
            or "douche" in desc_lower
            or "robinet" in desc_lower
        ):
            titre = "Travaux de plomberie sanitaire et évacuation"
            items.append(
                QuoteItem(
                    description="Tuyaux PVC évacuation DN 50 et DN 100",
                    quantite=4.0,
                    unite="barre 4m",
                    prix_unitaire=6500,
                    total=26000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Vannes d'arrêt et raccords laiton 1/2",
                    quantite=4.0,
                    unite="unité",
                    prix_unitaire=4500,
                    total=18000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Colle PVC, téflon et colliers de fixation",
                    quantite=1.0,
                    unite="forfait",
                    prix_unitaire=8000,
                    total=8000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Main d'œuvre remplacement tuyauterie et tests pression",
                    quantite=1.0,
                    unite="forfait",
                    prix_unitaire=30000,
                    total=30000,
                    type_item="MAIN_D_OEUVRE",
                )
            )
        else:
            titre = "Prestations de travaux et fournitures"
            items.append(
                QuoteItem(
                    description="Fournitures de chantier et quincaillerie",
                    quantite=1.0,
                    unite="forfait",
                    prix_unitaire=25000,
                    total=25000,
                    type_item="FOURNITURE",
                )
            )
            items.append(
                QuoteItem(
                    description="Main d'œuvre d'exécution",
                    quantite=1.0,
                    unite="forfait",
                    prix_unitaire=30000,
                    total=30000,
                    type_item="MAIN_D_OEUVRE",
                )
            )

        return QuoteExtractResponse(
            titre=titre,
            client_nom=client_nom or "Client Particulier",
            client_telephone=client_telephone,
            client_adresse="Abidjan",
            items=items,
            delai_estime_jours=3,
            recommandations=[
                "Prévoir le versement d'un acompte de 30% à 50% avant approvisionnement des matériaux.",
                "Faire valider l'emplacement des réseaux avant percement.",
            ],
        )

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
