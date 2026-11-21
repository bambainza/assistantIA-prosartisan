"""
Service de calculateurs techniques métiers déterministes pour ProsArtisan.

Fournit des algorithmes certifiés pour :
1. Dosage de béton et mortier (Maçonnerie / BTP).
2. Dimensionnement de section de câbles et calibres disjoncteurs (Électricité NF C 15-100).
3. Pente et diamètres d'évacuation sanitaire (Plomberie DTU 60.11).
4. Quantités de carrelage, colle et peinture (Finitions / Second œuvre).
5. Bilan thermique et puissance de climatisation (Froid tropical).
6. Nombre d'agglos et mortier de pose d'un mur (Maçonnerie).
7. Conversions d'unités de chantier (sacs, brouettes, seaux, m³, litres, kg).

Ces fonctions sont déterministes et utilisables directement par l'application ou
invoquées sous forme de Tools / Function Calling par le LLM.
"""

from __future__ import annotations

import math
from typing import Any

CLASSES_CIMENT: tuple[str, ...] = ("CPJ 42.5", "CPJ 32.5")
# Ouvrages porteurs dont le dosage est relevé avec un ciment CPJ 32.5.
OUVRAGES_STRUCTURE: frozenset[str] = frozenset(
    {"fondation_semelle", "poteau_poutre_dalle"}
)
SURDOSAGE_CPJ_32_5_KG_M3 = 50

# ── Électricité : calibre maximal du disjoncteur par section de conducteur ──
# Valeurs prudentes pour l'habitat (conducteurs isolés PVC sous conduit
# encastré, 2 conducteurs chargés, température ambiante ≤ 30 °C), alignées sur
# les tableaux usuels NF C 15-100 du logement : 1,5 mm² → 16 A, 2,5 mm² → 20 A,
# 4 mm² → 25 A, 6 mm² → 32 A, 10 mm² → 40 A. Au-delà, valeurs inférieures au
# courant admissible Iz de la méthode de référence B (CEI 60364-5-52).
# Lecture : un disjoncteur de calibre In protège la section S si In ≤ table[S].
# À faire valider par un électricien qualifié avant toute évolution.
CALIBRE_MAX_DISJONCTEUR_CUIVRE_A: dict[float, int] = {
    1.5: 16,
    2.5: 20,
    4.0: 25,
    6.0: 32,
    10.0: 40,
    16.0: 63,
    25.0: 80,
    35.0: 100,
    50.0: 125,
    70.0: 160,
    95.0: 200,
}
# Aluminium : section minimale 16 mm² ; courants admissibles ≈ 78 % du cuivre.
CALIBRE_MAX_DISJONCTEUR_ALUMINIUM_A: dict[float, int] = {
    16.0: 50,
    25.0: 63,
    35.0: 80,
    50.0: 100,
    70.0: 125,
    95.0: 160,
}
CALIBRES_DISJONCTEUR_A: tuple[int, ...] = (
    10,
    16,
    20,
    25,
    32,
    40,
    50,
    63,
    80,
    100,
    125,
    160,
    200,
)
HYPOTHESES_CABLE = (
    "Conducteurs isolés PVC sous conduit encastré, 2 conducteurs chargés, "
    "ambiance ≤ 30 °C, circuit non groupé. Pour un autre mode de pose, une "
    "ambiance plus chaude ou des circuits groupés, faire vérifier la section "
    "par un électricien qualifié."
)

# ── Maçonnerie : agglos (parpaings) 40 × 20 cm ──
AGGLOS_PAR_M2 = 12.5  # face 0,40 m × 0,20 m
# Volume de mortier de pose par m² de mur, selon l'épaisseur de l'agglo
# (joints de 1 à 1,5 cm, agglos creux) — ratios usuels de chantier.
MORTIER_POSE_M3_PAR_M2: dict[int, float] = {10: 0.012, 15: 0.018, 20: 0.024}
DOSAGE_MORTIER_POSE_KG_M3 = 300  # cohérent avec `mortier_pose_parpaing`
SABLE_MORTIER_POSE_LITRES_M3 = 1000

# ── Conversions d'unités de chantier ──
# Volumes en litres. Brouette « rase » de chantier = 60 L (convention déjà
# utilisée par le dosage béton) ; seau de maçon = 10 L.
UNITES_VOLUME_LITRES: dict[str, float] = {
    "litre": 1.0,
    "m3": 1000.0,
    "brouette": 60.0,
    "seau": 10.0,
}
# Masses en kg. Le sac n'a de sens que pour le ciment (sac de 50 kg).
UNITES_MASSE_KG: dict[str, float] = {"kg": 1.0, "tonne": 1000.0, "sac": 50.0}
# Masses volumiques apparentes moyennes (kg par litre, matériau sec en vrac).
MASSES_VOLUMIQUES_KG_L: dict[str, float] = {
    "ciment": 1.4,
    "sable": 1.6,
    "gravier": 1.5,
    "eau": 1.0,
}
ALIAS_UNITES: dict[str, str] = {
    "l": "litre",
    "litres": "litre",
    "m³": "m3",
    "metre_cube": "m3",
    "brouettes": "brouette",
    "seaux": "seau",
    "sacs": "sac",
    "sac_ciment": "sac",
    "tonnes": "tonne",
    "t": "tonne",
    "kilogramme": "kg",
}


class CalculatorService:
    """Service d'outils et calculateurs techniques de chantier."""

    # ── 1. MAÇONNERIE / BTP : BÉTON & MORTIER ────────────────────────────────

    @staticmethod
    def calculer_dosage_beton(
        volume_m3: float | None = None,
        longueur_m: float | None = None,
        largeur_m: float | None = None,
        epaisseur_m: float | None = None,
        type_ouvrage: str = "poteau_poutre_dalle",
        classe_ciment: str = "CPJ 42.5",
    ) -> dict[str, Any]:
        """Calcule avec précision les quantités de ciment, sable, gravier et eau.

        Args:
            volume_m3: Volume direct en m³, ou calculé via longueur x largeur x epaisseur.
            longueur_m: Longueur en mètres (si volume_m3 non fourni).
            largeur_m: Largeur en mètres (si volume_m3 non fourni).
            epaisseur_m: Épaisseur/Hauteur en mètres (si volume_m3 non fourni).
            type_ouvrage: 'beton_proprete', 'fondation_semelle', 'poteau_poutre_dalle',
                          'mortier_pose_parpaing', 'mortier_enduit_chape'.
            classe_ciment: 'CPJ 42.5' ou 'CPJ 32.5'.
        """
        if volume_m3 is None:
            if longueur_m and largeur_m and epaisseur_m:
                volume_m3 = round(longueur_m * largeur_m * epaisseur_m, 3)
            else:
                raise ValueError(
                    "Veuillez fournir volume_m3 ou le trio (longueur_m, largeur_m, epaisseur_m)."
                )

        if volume_m3 <= 0:
            raise ValueError("Le volume d'ouvrage doit être strictement supérieur à 0.")

        # Paramétrage des formules de dosage par m³
        # Ratios standard chantier Afrique de l'Ouest (brouette standard = 60 litres utiles)
        recettes: dict[str, dict[str, Any]] = {
            "beton_proprete": {
                "nom": "Béton de propreté / Gros béton non armé",
                "dosage_ciment_kg_m3": 250,
                "sable_litres_m3": 500,
                "gravier_litres_m3": 800,
                "eau_litres_m3": 125,
                "usage": "Fond de fouille, assise non porteuse.",
            },
            "fondation_semelle": {
                "nom": "Béton armé de fondation / Semelles filantes et isolées",
                "dosage_ciment_kg_m3": 350,
                "sable_litres_m3": 450,
                "gravier_litres_m3": 850,
                "eau_litres_m3": 175,
                "usage": "Semelles de fondation, longrines de redressement.",
            },
            "poteau_poutre_dalle": {
                "nom": "Béton armé de structure (Poteaux, Poutres, Dalles, Linteaux)",
                "dosage_ciment_kg_m3": 350,
                "sable_litres_m3": 400,
                "gravier_litres_m3": 800,
                "eau_litres_m3": 175,
                "usage": "Éléments porteurs principaux sollicités en flexion/compression.",
            },
            "mortier_pose_parpaing": {
                "nom": "Mortier de pose pour blocs de ciment (parpaings de 15 et 20)",
                "dosage_ciment_kg_m3": 300,
                "sable_litres_m3": 1000,
                "gravier_litres_m3": 0,
                "eau_litres_m3": 150,
                "usage": "Hourdage et montage des murs en agglos.",
            },
            "mortier_enduit_chape": {
                "nom": "Mortier d'enduit mural et chape de sol",
                "dosage_ciment_kg_m3": 400,
                "sable_litres_m3": 1000,
                "gravier_litres_m3": 0,
                "eau_litres_m3": 180,
                "usage": "Corps d'enduit (gobetis/corroyage) et chape lisse.",
            },
        }

        recette = recettes.get(type_ouvrage)
        if recette is None:
            # Jamais de bascule silencieuse vers une autre recette : un dosage
            # de structure appliqué à un enduit (ou l'inverse) fausse la commande.
            raise ValueError(
                f"type_ouvrage '{type_ouvrage}' inconnu. Valeurs acceptées : "
                + ", ".join(sorted(recettes))
                + "."
            )
        if classe_ciment not in CLASSES_CIMENT:
            raise ValueError(
                f"classe_ciment '{classe_ciment}' inconnue. Valeurs acceptées : "
                + ", ".join(CLASSES_CIMENT)
                + "."
            )

        dosage_kg_m3 = recette["dosage_ciment_kg_m3"]
        ajustement_kg_m3 = 0
        if classe_ciment == "CPJ 32.5" and type_ouvrage in OUVRAGES_STRUCTURE:
            # Un CPJ 32.5 est moins résistant qu'un CPJ 42.5 : pour un béton
            # armé porteur, on compense par un dosage plus riche (pratique
            # courante : 350 kg/m³ en 42.5 ↔ 400 kg/m³ en 32.5).
            ajustement_kg_m3 = SURDOSAGE_CPJ_32_5_KG_M3
            dosage_kg_m3 += ajustement_kg_m3

        # Calcul des totaux bruts
        poids_ciment_total_kg = round(dosage_kg_m3 * volume_m3, 1)
        # Sacs de ciment de 50 kg (arrondi au sac supérieur pour sécurité chantier)
        sacs_ciment_50kg = math.ceil(poids_ciment_total_kg / 50.0)

        sable_total_litres = round(recette["sable_litres_m3"] * volume_m3, 1)
        sable_total_m3 = round(sable_total_litres / 1000.0, 2)
        sable_brouettes_60l = round(sable_total_litres / 60.0, 1)

        gravier_total_litres = round(recette["gravier_litres_m3"] * volume_m3, 1)
        gravier_total_m3 = round(gravier_total_litres / 1000.0, 2)
        gravier_brouettes_60l = round(gravier_total_litres / 60.0, 1)

        eau_totale_litres = round(recette["eau_litres_m3"] * volume_m3, 1)

        return {
            "type_ouvrage": recette["nom"],
            "volume_m3": volume_m3,
            "classe_ciment": classe_ciment,
            "dosage_ciment_kg_m3": dosage_kg_m3,
            "ajustement_classe_ciment_kg_m3": ajustement_kg_m3,
            "resultats": {
                "ciment_poids_kg": poids_ciment_total_kg,
                "sacs_ciment_50kg": sacs_ciment_50kg,
                "sable_m3": sable_total_m3,
                "sable_litres": sable_total_litres,
                "sable_brouettes_60l": sable_brouettes_60l,
                "gravier_m3": gravier_total_m3,
                "gravier_litres": gravier_total_litres,
                "gravier_brouettes_60l": gravier_brouettes_60l,
                "eau_litres": eau_totale_litres,
            },
            "conseils_chantier": [
                "Utiliser du sable de lagune ou de carrière propre, sans traces d'argile.",
                "Enrobage minimal des armatures : 3 cm en intérieur, 5 cm en zone humide/lagunaire.",
                "Arroser le béton 2 fois par jour pendant 7 jours après coulage pour éviter la dessiccation.",
                "Temps de décoffrage minimal : 3 jours pour les joues de poteaux, 21 à 28 jours sous les dalles et poutres.",
            ],
        }

    # ── 2. ÉLECTRICITÉ : SECTION DE CÂBLE & PROTECTION ───────────────────────

    @staticmethod
    def calculer_section_cable(
        puissance_watts: float | None = None,
        intensite_amperes: float | None = None,
        longueur_metres: float = 10.0,
        tension_volts: int = 230,
        type_alimentation: str = "monophase",
        chute_tension_max_pct: float = 3.0,
        nature_conducteur: str = "cuivre",
        cos_phi: float = 0.9,
    ) -> dict[str, Any]:
        """Calcule la section normalisée de conducteur et le calibre de disjoncteur (NF C 15-100).

        Args:
            puissance_watts: Puissance cumulée des récepteurs en Watts.
            intensite_amperes: Intensité nominale en Ampères (si puissance non fournie).
            longueur_metres: Longueur aller simple du circuit en mètres.
            tension_volts: 230 (monophasé) ou 400 (triphasé).
            type_alimentation: 'monophase' ou 'triphase'.
            chute_tension_max_pct: Tolérance max (3% éclairage, 5% force motrice/prises).
            nature_conducteur: 'cuivre' (résistivité 0.0175 Ω.mm²/m) ou 'aluminium' (0.028 Ω.mm²/m).
            cos_phi: Facteur de puissance moyen (0.85 - 0.95).
        """
        if intensite_amperes is None:
            if puissance_watts is None or puissance_watts <= 0:
                raise ValueError(
                    "Veuillez renseigner au moins puissance_watts (>0) ou intensite_amperes (>0)."
                )
            if type_alimentation == "triphase" or tension_volts >= 380:
                intensite_amperes = puissance_watts / (
                    math.sqrt(3) * tension_volts * cos_phi
                )
            else:
                intensite_amperes = puissance_watts / (tension_volts * cos_phi)

        intensite_amperes = round(intensite_amperes, 2)
        if intensite_amperes <= 0:
            raise ValueError("L'intensité calculée doit être positive.")
        if nature_conducteur.lower() not in {"cuivre", "aluminium"}:
            raise ValueError("nature_conducteur doit valoir 'cuivre' ou 'aluminium'.")
        if longueur_metres <= 0:
            raise ValueError("La longueur du circuit doit être strictement positive.")

        # Résistivité électrique ρ (Ohm.mm²/m)
        rho = 0.0175 if nature_conducteur.lower() == "cuivre" else 0.028

        # Chute de tension admissible en Volts
        delta_u_max_v = (chute_tension_max_pct / 100.0) * tension_volts

        # Formule de section minimale S (mm²)
        if type_alimentation == "triphase" or tension_volts >= 380:
            # Triphasé équilibré : ΔU = √3 * ρ * L * I * cos(φ) / S
            section_theorique_mm2 = (
                math.sqrt(3) * rho * longueur_metres * intensite_amperes * cos_phi
            ) / delta_u_max_v
        else:
            # Monophasé : ΔU = 2 * ρ * L * I * cos(φ) / S
            section_theorique_mm2 = (
                2 * rho * longueur_metres * intensite_amperes * cos_phi
            ) / delta_u_max_v

        est_cuivre = nature_conducteur.lower() == "cuivre"
        table_calibres = (
            CALIBRE_MAX_DISJONCTEUR_CUIVRE_A
            if est_cuivre
            else CALIBRE_MAX_DISJONCTEUR_ALUMINIUM_A
        )

        # Calibre disjoncteur normalisé recommandé : le plus petit In ≥ Ib.
        disjoncteur_recommande = next(
            (c for c in CALIBRES_DISJONCTEUR_A if c >= intensite_amperes), None
        )
        if disjoncteur_recommande is None or disjoncteur_recommande > max(
            table_calibres.values()
        ):
            # Jamais de section « par défaut » sous-dimensionnée : au-delà de la
            # table, l'installation relève d'une étude spécifique.
            raise ValueError(
                f"Intensité de {intensite_amperes} A hors du domaine de ce "
                "calculateur (habitat et petit tertiaire). Faire réaliser une "
                "étude par un électricien qualifié."
            )

        # Coordination NF C 15-100 : Ib ≤ In ≤ Iz. La section retenue est la
        # plus petite qui protège le calibre In ET respecte la chute de tension.
        section_retenue = next(
            (
                s
                for s, calibre_max in sorted(table_calibres.items())
                if s >= section_theorique_mm2 and calibre_max >= disjoncteur_recommande
            ),
            None,
        )
        if section_retenue is None:
            raise ValueError(
                "Aucune section normalisée de la table ne respecte à la fois le "
                f"calibre {disjoncteur_recommande} A et la chute de tension de "
                f"{chute_tension_max_pct} % sur {longueur_metres} m. Réduire la "
                "longueur, scinder le circuit ou faire réaliser une étude."
            )

        # Recalcul de la chute de tension réelle avec la section normalisée
        if type_alimentation == "triphase" or tension_volts >= 380:
            chute_reelle_v = (
                math.sqrt(3) * rho * longueur_metres * intensite_amperes * cos_phi
            ) / section_retenue
        else:
            chute_reelle_v = (
                2 * rho * longueur_metres * intensite_amperes * cos_phi
            ) / section_retenue
        chute_reelle_pct = round((chute_reelle_v / tension_volts) * 100.0, 2)

        return {
            "intensite_a": intensite_amperes,
            "puissance_w": round(
                puissance_watts or (intensite_amperes * tension_volts * cos_phi), 1
            ),
            "tension_v": tension_volts,
            "longueur_m": longueur_metres,
            "section_theorique_mm2": round(section_theorique_mm2, 2),
            "section_normalisee_recommandee_mm2": section_retenue,
            "disjoncteur_protection_recommande_a": disjoncteur_recommande,
            "chute_tension_reelle_pct": chute_reelle_pct,
            "chute_tension_reelle_v": round(chute_reelle_v, 2),
            "conformite_norme": chute_reelle_pct <= chute_tension_max_pct,
            "nature_conducteur": "cuivre" if est_cuivre else "aluminium",
            "hypotheses": HYPOTHESES_CABLE,
            "recommandations": [
                f"Utiliser un disjoncteur divisionnaire calibré à {disjoncteur_recommande}A (Courbe C pour usage général, Courbe D si moteur/climatiseur).",
                "Protéger le circuit par un interrupteur différentiel 30mA type AC ou type A.",
                "Ne jamais panacher des sections différentes sur un même circuit aval.",
            ],
        }

    # ── 3. PLOMBERIE : PENTE & DIAMÈTRES D'ÉVACUATION ────────────────────────

    @staticmethod
    def calculer_evacuation_plomberie(
        type_appareil: str = "wc",
        longueur_canalisation_m: float = 4.0,
        pente_souhaitee_pct: float = 2.0,
    ) -> dict[str, Any]:
        """Détermine les diamètres nominaux (DN PVC) et le dénivelé selon les règles DTU 60.11.

        Args:
            type_appareil: 'wc', 'douche_italienne', 'baignoire', 'lavabo', 'evier_cuisine',
                           'machine_a_laver', 'collecteur_principal'.
            longueur_canalisation_m: Longueur du parcours d'évacuation en mètres.
            pente_souhaitee_pct: Pente en % ou cm/m (1% min, 2% recommandé, 3% max).
        """
        appareils: dict[str, dict[str, Any]] = {
            "wc": {
                "nom": "WC / Cuvette d'aisance",
                "dn_individuel_min_mm": 100,
                "pente_recommandee_pct": 2.0,
                "observations": "Raccordement direct sans réduction. Prévoir clapet aérateur de chute si étage.",
            },
            "douche_italienne": {
                "nom": "Douche / Douche à l'italienne",
                "dn_individuel_min_mm": 50,
                "pente_recommandee_pct": 2.0,
                "observations": "Préférer DN 50 au DN 40 pour éviter les débordements de bonde plate.",
            },
            "baignoire": {
                "nom": "Baignoire",
                "dn_individuel_min_mm": 40,
                "pente_recommandee_pct": 2.0,
                "observations": "Garder une garde d'eau siphon d'au moins 50 mm.",
            },
            "lavabo": {
                "nom": "Lavabo / Lave-mains",
                "dn_individuel_min_mm": 32,
                "pente_recommandee_pct": 2.0,
                "observations": "DN 32 suffisant jusqu'à 2 m, passer en DN 40 au-delà.",
            },
            "evier_cuisine": {
                "nom": "Évier de cuisine / Lave-vaisselle",
                "dn_individuel_min_mm": 50,
                "pente_recommandee_pct": 2.5,
                "observations": "DN 50 fortement conseillé contre les dépôts de graisses ménagères.",
            },
            "machine_a_laver": {
                "nom": "Machine à laver le linge",
                "dn_individuel_min_mm": 40,
                "pente_recommandee_pct": 2.0,
                "observations": "Hauteur de crosse de vidange entre 60 cm et 90 cm du sol.",
            },
            "collecteur_principal": {
                "nom": "Collecteur principal / Chute d'eaux usées et vannes (EU/EV)",
                "dn_individuel_min_mm": 110,
                "pente_recommandee_pct": 2.0,
                "observations": "Ventilation primaire en toiture obligatoire de même diamètre.",
            },
        }

        app_info = appareils.get(type_appareil, appareils["wc"])
        pente_retenue = max(1.0, min(pente_souhaitee_pct, 4.0))
        denivele_total_cm = round(longueur_canalisation_m * pente_retenue, 1)

        return {
            "appareil": app_info["nom"],
            "diametre_nominal_pvc_mm": app_info["dn_individuel_min_mm"],
            "longueur_m": longueur_canalisation_m,
            "pente_pct": pente_retenue,
            "pente_cm_par_metre": pente_retenue,
            "denivele_requis_cm": denivele_total_cm,
            "observations": app_info["observations"],
            "bonnes_pratiques": [
                "Utiliser des coudes à 45° plutôt que des coudes à 90° vifs pour éviter les engorgements.",
                "Dépolir et dégraisser au solvant PVC avant d'encoller.",
                "Respecter la garde d'eau minimale des siphons (50 mm) contre les remontées d'odeurs.",
            ],
        }

    # ── 4. REVÊTEMENTS : CARRELAGE, COLLE & PEINTURE ─────────────────────────

    @staticmethod
    def calculer_carrelage_et_colle(
        surface_m2: float,
        format_carreau_cm: str = "60x60",
        type_pose: str = "droite",
        sac_colle_kg: int = 25,
    ) -> dict[str, Any]:
        """Calcule les surfaces de carreaux, marge de chutes, sacs de mortier colle et joints.

        Args:
            surface_m2: Surface nette du sol ou du mur en m².
            format_carreau_cm: '30x30', '40x40', '60x60', '60x120', etc.
            type_pose: 'droite' (marge +10%), 'diagonale' (marge +15%), 'chevron' (marge +15%).
            sac_colle_kg: Conditionnement standard (25 kg).
        """
        if surface_m2 <= 0:
            raise ValueError("La surface doit être strictement positive.")

        marge_pct = 15.0 if type_pose in {"diagonale", "chevron"} else 10.0
        surface_avec_chutes_m2 = round(surface_m2 * (1.0 + marge_pct / 100.0), 2)

        conso_colle_kg_par_m2 = 6.0  # kg/m² en double encollage
        poids_colle_total_kg = round(surface_m2 * conso_colle_kg_par_m2, 1)
        sacs_colle_25kg = math.ceil(poids_colle_total_kg / sac_colle_kg)

        poids_joint_kg = round(surface_m2 * 0.4, 1)
        sacs_joint_5kg = math.ceil(poids_joint_kg / 5.0)

        return {
            "surface_nette_m2": surface_m2,
            "type_pose": type_pose,
            "marge_chutes_pct": marge_pct,
            "surface_a_commander_m2": surface_avec_chutes_m2,
            "mortier_colle": {
                "conso_kg_m2": conso_colle_kg_par_m2,
                "poids_total_kg": poids_colle_total_kg,
                "sacs_25kg": sacs_colle_25kg,
                "mode_application": "Double encollage conseillé (peigne 8-10 mm + beurrage dos de carreau).",
            },
            "mortier_joint": {
                "poids_total_kg": poids_joint_kg,
                "sacs_5kg": sacs_joint_5kg,
            },
            "conseils": [
                "Vérifier la planéité du support à la règle de 2 m (tolérance max 5 mm).",
                "Utiliser des croisillons autonivelants pour les grands formats (60x60 et plus).",
                "Respecter un joint périphérique de désolidarisation de 5 mm au pied des murs.",
            ],
        }

    # ── 5. FROID & CLIMATISATION : BILAN THERMIQUE TROPICAL ───────────────────

    @staticmethod
    def calculer_bilan_climatisation(
        surface_m2: float,
        hauteur_plafond_m: float = 2.8,
        type_toiture: str = "dalle_beton",
        exposition_soleil: str = "moyenne",
        nombre_personnes: int = 2,
    ) -> dict[str, Any]:
        """Calcule la puissance frigorifique recommandée en climat tropical (BTU/h et CV).

        Args:
            surface_m2: Surface au sol en m².
            hauteur_plafond_m: Hauteur sous plafond (standard 2.8 m).
            type_toiture: 'dalle_beton', 'toit_tole_isole', 'toit_tole_non_isole'.
            exposition_soleil: 'faible' (ombragé/nord), 'moyenne', 'forte' (ouest/grandes baies vitrées).
            nombre_personnes: Nombre habituel d'occupants dans la pièce.
        """
        if surface_m2 <= 0:
            raise ValueError("La surface doit être strictement positive.")

        volume_m3 = surface_m2 * hauteur_plafond_m
        base_w_m3 = 50.0

        if type_toiture == "toit_tole_non_isole":
            base_w_m3 += 20.0
        elif type_toiture == "toit_tole_isole":
            base_w_m3 += 8.0

        if exposition_soleil == "forte":
            base_w_m3 += 15.0
        elif exposition_soleil == "faible":
            base_w_m3 -= 5.0

        puissance_thermique_w = volume_m3 * base_w_m3
        puissance_thermique_w += (nombre_personnes * 100) + 150
        puissance_btu = puissance_thermique_w * 3.41214

        splits = [
            {"nom": "Split 1.0 CV (9 000 BTU)", "btu": 9000, "puissance_cv": 1.0},
            {"nom": "Split 1.5 CV (12 000 BTU)", "btu": 12000, "puissance_cv": 1.5},
            {"nom": "Split 2.0 CV (18 000 BTU)", "btu": 18000, "puissance_cv": 2.0},
            {"nom": "Split 2.5 CV (24 000 BTU)", "btu": 24000, "puissance_cv": 2.5},
            {"nom": "Split 3.0 CV (30 000 BTU)", "btu": 30000, "puissance_cv": 3.0},
        ]

        split_recommande = splits[-1]
        for sp in splits:
            if sp["btu"] >= puissance_btu * 0.95:
                split_recommande = sp
                break

        return {
            "surface_m2": surface_m2,
            "volume_m3": round(volume_m3, 1),
            "besoin_calcule_btu": round(puissance_btu),
            "besoin_calcule_kw": round(puissance_thermique_w / 1000.0, 2),
            "modele_recommande": split_recommande["nom"],
            "puissance_cv": split_recommande["puissance_cv"],
            "puissance_btu_commerciale": split_recommande["btu"],
            "conseils_installation": [
                "Placer l'unité extérieure à l'abri du rayonnement solaire direct de l'après-midi pour optimiser le rendement.",
                "Circuit dédié par climatiseur : 2.5 mm² jusqu'à 1.5 CV, 4 mm² à partir de 2 CV, disjoncteur divisionnaire 16A ou 20A courbe C (vérifier le calibre exigé par le fabricant).",
                "Tirer au vide l'installation pendant au moins 15 minutes avant ouverture des vannes frigorifiques.",
            ],
        }

    # ── 6. MAÇONNERIE : MUR EN AGGLOS (PARPAINGS) ───────────────────────────

    @staticmethod
    def calculer_agglos_mur(
        longueur_m: float,
        hauteur_m: float,
        surface_ouvertures_m2: float = 0.0,
        epaisseur_agglo_cm: int = 15,
        pertes_pct: float = 5.0,
    ) -> dict[str, Any]:
        """Calcule le nombre d'agglos 40 × 20 cm et le mortier de pose d'un mur.

        Args:
            longueur_m: Longueur du mur en mètres.
            hauteur_m: Hauteur du mur en mètres.
            surface_ouvertures_m2: Surface des portes et fenêtres à déduire (m²).
            epaisseur_agglo_cm: 10 (cloison), 15 (mur courant) ou 20 (porteur).
            pertes_pct: Casse et coupes (5 % par défaut, 0 à 20 %).
        """
        if longueur_m <= 0 or hauteur_m <= 0:
            raise ValueError("La longueur et la hauteur du mur doivent être > 0.")
        if surface_ouvertures_m2 < 0:
            raise ValueError("La surface des ouvertures ne peut pas être négative.")
        if epaisseur_agglo_cm not in MORTIER_POSE_M3_PAR_M2:
            raise ValueError(
                "epaisseur_agglo_cm doit valoir 10, 15 ou 20 (agglos 40 × 20 cm)."
            )
        if not 0 <= pertes_pct <= 20:
            raise ValueError("pertes_pct doit être compris entre 0 et 20.")

        surface_brute_m2 = round(longueur_m * hauteur_m, 2)
        surface_nette_m2 = round(surface_brute_m2 - surface_ouvertures_m2, 2)
        if surface_nette_m2 <= 0:
            raise ValueError("Les ouvertures dépassent la surface du mur.")

        agglos_net = surface_nette_m2 * AGGLOS_PAR_M2
        agglos_a_commander = math.ceil(agglos_net * (1 + pertes_pct / 100.0))

        mortier_m3 = round(
            surface_nette_m2 * MORTIER_POSE_M3_PAR_M2[epaisseur_agglo_cm], 3
        )
        ciment_kg = round(mortier_m3 * DOSAGE_MORTIER_POSE_KG_M3, 1)
        sable_litres = round(mortier_m3 * SABLE_MORTIER_POSE_LITRES_M3, 1)

        return {
            "surface_brute_m2": surface_brute_m2,
            "surface_ouvertures_m2": surface_ouvertures_m2,
            "surface_nette_m2": surface_nette_m2,
            "epaisseur_agglo_cm": epaisseur_agglo_cm,
            "agglos_par_m2": AGGLOS_PAR_M2,
            "pertes_pct": pertes_pct,
            "resultats": {
                "agglos_unites": agglos_a_commander,
                "mortier_pose_m3": mortier_m3,
                "ciment_kg": ciment_kg,
                "sacs_ciment_50kg": math.ceil(ciment_kg / 50.0) if ciment_kg else 0,
                "sable_m3": round(sable_litres / 1000.0, 2),
                "sable_brouettes_60l": round(sable_litres / 60.0, 1),
            },
            "conseils_chantier": [
                "Mortier de pose dosé à 300 kg/m³ (1 sac de ciment pour 2,5 à 3 brouettes de sable).",
                "Humidifier les agglos avant la pose par forte chaleur.",
                "Croiser les joints d'un rang à l'autre et chaîner horizontalement tous les 3 m de hauteur.",
            ],
        }

    # ── 7. CONVERSIONS D'UNITÉS DE CHANTIER ─────────────────────────────────

    @staticmethod
    def convertir_unites_chantier(
        valeur: float,
        unite_source: str,
        unite_cible: str,
        materiau: str | None = None,
    ) -> dict[str, Any]:
        """Convertit entre unités de chantier (sacs, brouettes, seaux, m³, litres, kg).

        Args:
            valeur: Quantité à convertir (> 0).
            unite_source: litre, m3, brouette (60 L), seau (10 L), kg, tonne, sac (ciment 50 kg).
            unite_cible: Même liste d'unités.
            materiau: ciment, sable, gravier ou eau — requis pour passer d'un
                volume à une masse (ou l'inverse) et pour toute conversion en sacs.
        """
        if valeur <= 0:
            raise ValueError("La valeur à convertir doit être strictement positive.")

        def _normaliser(unite: str) -> str:
            u = unite.strip().lower()
            u = ALIAS_UNITES.get(u, u)
            if u not in UNITES_VOLUME_LITRES and u not in UNITES_MASSE_KG:
                raise ValueError(
                    f"Unité '{unite}' inconnue. Unités acceptées : "
                    + ", ".join([*UNITES_VOLUME_LITRES, *UNITES_MASSE_KG])
                    + "."
                )
            return u

        source = _normaliser(unite_source)
        cible = _normaliser(unite_cible)
        mat = materiau.strip().lower() if materiau else None
        if mat is not None and mat not in MASSES_VOLUMIQUES_KG_L:
            raise ValueError(
                f"Matériau '{materiau}' inconnu. Matériaux acceptés : "
                + ", ".join(MASSES_VOLUMIQUES_KG_L)
                + "."
            )
        if "sac" in (source, cible) and mat != "ciment":
            raise ValueError(
                "L'unité 'sac' désigne un sac de ciment de 50 kg : préciser materiau='ciment'."
            )

        source_volume = source in UNITES_VOLUME_LITRES
        cible_volume = cible in UNITES_VOLUME_LITRES
        if source_volume != cible_volume and mat is None:
            raise ValueError(
                "Passer d'un volume à une masse exige le matériau (ciment, sable, gravier ou eau)."
            )

        if source_volume:
            litres = valeur * UNITES_VOLUME_LITRES[source]
            kg = litres * MASSES_VOLUMIQUES_KG_L[mat] if mat else None
        else:
            kg = valeur * UNITES_MASSE_KG[source]
            litres = kg / MASSES_VOLUMIQUES_KG_L[mat] if mat else None

        resultat = (
            litres / UNITES_VOLUME_LITRES[cible]
            if cible_volume
            else kg / UNITES_MASSE_KG[cible]  # type: ignore[operator]
        )

        hypotheses = [
            "Brouette rase de chantier = 60 litres ; seau de maçon = 10 litres.",
        ]
        if mat:
            hypotheses.append(
                f"Masse volumique apparente du {mat} sec en vrac : "
                f"{MASSES_VOLUMIQUES_KG_L[mat]} kg/litre (valeur moyenne, varie avec l'humidité)."
            )
        if "sac" in (source, cible):
            hypotheses.append("Sac de ciment = 50 kg.")

        return {
            "valeur": valeur,
            "unite_source": source,
            "unite_cible": cible,
            "materiau": mat,
            "resultat": round(resultat, 3),
            "hypotheses": hypotheses,
        }

    # ── MISTRAL / OPENAI FUNCTION CALLING DEFINITIONS ────────────────────────

    @classmethod
    def get_tool_definitions(cls) -> list[dict[str, Any]]:
        """Retourne la spécification JSON Schema des calculateurs pour les LLMs."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "calculer_dosage_beton",
                    "description": "Calcule les quantités exactes de ciment (sacs de 50kg), sable et gravier (m³ et brouettes) et eau pour un ouvrage de maçonnerie/BTP.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "volume_m3": {
                                "type": "number",
                                "description": "Volume d'ouvrage en m³",
                            },
                            "longueur_m": {
                                "type": "number",
                                "description": "Longueur en mètres",
                            },
                            "largeur_m": {
                                "type": "number",
                                "description": "Largeur en mètres",
                            },
                            "epaisseur_m": {
                                "type": "number",
                                "description": "Épaisseur ou hauteur en mètres",
                            },
                            "type_ouvrage": {
                                "type": "string",
                                "enum": [
                                    "beton_proprete",
                                    "fondation_semelle",
                                    "poteau_poutre_dalle",
                                    "mortier_pose_parpaing",
                                    "mortier_enduit_chape",
                                ],
                                "description": "Type d'élément à réaliser",
                            },
                            "classe_ciment": {
                                "type": "string",
                                "enum": ["CPJ 42.5", "CPJ 32.5"],
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculer_section_cable",
                    "description": "Calcule la section de câble cuivre (mm²) et le calibre de disjoncteur (A) requis selon la puissance, distance et tolérance de chute de tension (NF C 15-100).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "puissance_watts": {
                                "type": "number",
                                "description": "Puissance cumulée en Watts",
                            },
                            "intensite_amperes": {
                                "type": "number",
                                "description": "Intensité en Ampères",
                            },
                            "longueur_metres": {
                                "type": "number",
                                "description": "Distance aller simple en mètres",
                            },
                            "tension_volts": {
                                "type": "integer",
                                "description": "230 (monophasé) ou 400 (triphasé)",
                            },
                            "type_alimentation": {
                                "type": "string",
                                "enum": ["monophase", "triphase"],
                            },
                            "chute_tension_max_pct": {
                                "type": "number",
                                "description": "Tolérance max (3% éclairage, 5% force)",
                            },
                            "nature_conducteur": {
                                "type": "string",
                                "enum": ["cuivre", "aluminium"],
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculer_agglos_mur",
                    "description": "Calcule le nombre d'agglos (parpaings 40x20 cm) d'un mur, avec pertes, et le mortier de pose (sacs de ciment, sable).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "longueur_m": {
                                "type": "number",
                                "description": "Longueur du mur en mètres",
                            },
                            "hauteur_m": {
                                "type": "number",
                                "description": "Hauteur du mur en mètres",
                            },
                            "surface_ouvertures_m2": {
                                "type": "number",
                                "description": "Surface des portes et fenêtres à déduire (m²)",
                            },
                            "epaisseur_agglo_cm": {
                                "type": "integer",
                                "enum": [10, 15, 20],
                                "description": "Épaisseur de l'agglo en cm",
                            },
                            "pertes_pct": {
                                "type": "number",
                                "description": "Casse et coupes en % (5 par défaut)",
                            },
                        },
                        "required": ["longueur_m", "hauteur_m"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "convertir_unites_chantier",
                    "description": "Convertit une quantité entre unités de chantier : sacs de ciment (50 kg), brouettes (60 L), seaux (10 L), m³, litres, kg, tonnes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "valeur": {
                                "type": "number",
                                "description": "Quantité à convertir",
                            },
                            "unite_source": {
                                "type": "string",
                                "enum": [
                                    "litre",
                                    "m3",
                                    "brouette",
                                    "seau",
                                    "kg",
                                    "tonne",
                                    "sac",
                                ],
                            },
                            "unite_cible": {
                                "type": "string",
                                "enum": [
                                    "litre",
                                    "m3",
                                    "brouette",
                                    "seau",
                                    "kg",
                                    "tonne",
                                    "sac",
                                ],
                            },
                            "materiau": {
                                "type": "string",
                                "enum": ["ciment", "sable", "gravier", "eau"],
                                "description": "Requis pour passer d'un volume à une masse et pour les sacs",
                            },
                        },
                        "required": ["valeur", "unite_source", "unite_cible"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculer_evacuation_plomberie",
                    "description": "Détermine le diamètre PVC (DN en mm) et la dénivellation requise pour une évacuation sanitaire selon le DTU 60.11.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "type_appareil": {
                                "type": "string",
                                "enum": [
                                    "wc",
                                    "douche_italienne",
                                    "baignoire",
                                    "lavabo",
                                    "evier_cuisine",
                                    "machine_a_laver",
                                    "collecteur_principal",
                                ],
                            },
                            "longueur_canalisation_m": {
                                "type": "number",
                                "description": "Longueur du tuyau en mètres",
                            },
                            "pente_souhaitee_pct": {
                                "type": "number",
                                "description": "Pente en % (ex: 2.0 pour 2 cm/m)",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculer_carrelage_et_colle",
                    "description": "Calcule la surface de carreaux à commander (avec marge de chutes), ainsi que les sacs de colle et de joints.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "surface_m2": {
                                "type": "number",
                                "description": "Surface nette en m²",
                            },
                            "format_carreau_cm": {
                                "type": "string",
                                "description": "Format carreaux ex: 60x60",
                            },
                            "type_pose": {
                                "type": "string",
                                "enum": ["droite", "diagonale", "chevron"],
                            },
                        },
                        "required": ["surface_m2"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculer_bilan_climatisation",
                    "description": "Calcule la puissance frigorifique requise en climat tropical (BTU/h et CV) et recommande le modèle de Split adapté.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "surface_m2": {
                                "type": "number",
                                "description": "Surface de la pièce en m²",
                            },
                            "hauteur_plafond_m": {
                                "type": "number",
                                "description": "Hauteur sous plafond en mètres",
                            },
                            "type_toiture": {
                                "type": "string",
                                "enum": [
                                    "dalle_beton",
                                    "toit_tole_isole",
                                    "toit_tole_non_isole",
                                ],
                            },
                            "exposition_soleil": {
                                "type": "string",
                                "enum": ["faible", "moyenne", "forte"],
                            },
                            "nombre_personnes": {
                                "type": "integer",
                                "description": "Nombre d'occupants",
                            },
                        },
                        "required": ["surface_m2"],
                    },
                },
            },
        ]

    @classmethod
    def execute_tool(cls, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Exécute de façon sécurisée le calculateur métier correspondant au tool invoqué."""
        handlers: dict[str, Any] = {
            "calculer_dosage_beton": cls.calculer_dosage_beton,
            # Nom prévu par le cahier des charges, conservé comme alias.
            "calculer_materiaux_btp": cls.calculer_dosage_beton,
            "calculer_section_cable": cls.calculer_section_cable,
            "calculer_evacuation_plomberie": cls.calculer_evacuation_plomberie,
            "calculer_carrelage_et_colle": cls.calculer_carrelage_et_colle,
            "calculer_bilan_climatisation": cls.calculer_bilan_climatisation,
            "calculer_agglos_mur": cls.calculer_agglos_mur,
            "convertir_unites_chantier": cls.convertir_unites_chantier,
        }

        handler = handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Outil de calcul '{tool_name}' non reconnu.")

        try:
            return handler(**arguments)
        except TypeError as exc:
            # Paramètre inconnu ou manquant : erreur de saisie, pas une panne.
            raise ValueError(
                f"Paramètres invalides pour l'outil '{tool_name}' : {exc}"
            ) from exc


calculator_service = CalculatorService()
