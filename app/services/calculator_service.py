"""
Service de calculateurs techniques métiers déterministes pour ProsArtisan.

Fournit des algorithmes certifiés pour :
1. Dosage de béton et mortier (Maçonnerie / BTP).
2. Dimensionnement de section de câbles et calibres disjoncteurs (Électricité NF C 15-100).
3. Pente et diamètres d'évacuation sanitaire (Plomberie DTU 60.11).
4. Quantités de carrelage, colle et peinture (Finitions / Second œuvre).
5. Bilan thermique et puissance de climatisation (Froid tropical).

Ces fonctions sont déterministes et utilisables directement par l'application ou
invoquées sous forme de Tools / Function Calling par le LLM.
"""

from __future__ import annotations

import math
from typing import Any


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

        recette = recettes.get(type_ouvrage, recettes["poteau_poutre_dalle"])

        # Calcul des totaux bruts
        poids_ciment_total_kg = round(recette["dosage_ciment_kg_m3"] * volume_m3, 1)
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

        # Sections standards normalisées (mm²)
        sections_normalisees = [
            1.5,
            2.5,
            4.0,
            6.0,
            10.0,
            16.0,
            25.0,
            35.0,
            50.0,
            70.0,
            95.0,
        ]

        capacites_thermiques_cuivre: dict[float, float] = {
            1.5: 16.0,
            2.5: 25.0,
            4.0: 32.0,
            6.0: 40.0,
            10.0: 63.0,
            16.0: 80.0,
            25.0: 100.0,
            35.0: 125.0,
            50.0: 160.0,
            70.0: 200.0,
            95.0: 250.0,
        }

        # Calibre disjoncteur normalisé recommandé (In >= Ib)
        calibres_standard = [10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125]
        disjoncteur_recommande = None
        for c in calibres_standard:
            if c >= intensite_amperes:
                disjoncteur_recommande = c
                break
        if disjoncteur_recommande is None:
            disjoncteur_recommande = 125

        # Règle NF C 15-100 de coordination : Ib <= In <= Iz
        # Le câble doit supporter en continu au moins le calibre de protection In
        courant_dimensionnement_thermique = float(disjoncteur_recommande)

        section_retenue = None
        for s in sections_normalisees:
            if s >= section_theorique_mm2:
                i_adm = capacites_thermiques_cuivre.get(s, s * 4)
                if i_adm >= courant_dimensionnement_thermique:
                    section_retenue = s
                    break

        if section_retenue is None:
            section_retenue = sections_normalisees[-1]

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
                "Respecter une section de câble d'au moins 2.5 mm² pour 1.5 CV à 2.0 CV avec disjoncteur 16A/20A Courbe D.",
                "Tirer au vide l'installation pendant au moins 15 minutes avant ouverture des vannes frigorifiques.",
            ],
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
                        },
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
            "calculer_section_cable": cls.calculer_section_cable,
            "calculer_evacuation_plomberie": cls.calculer_evacuation_plomberie,
            "calculer_carrelage_et_colle": cls.calculer_carrelage_et_colle,
            "calculer_bilan_climatisation": cls.calculer_bilan_climatisation,
        }

        handler = handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Outil de calcul '{tool_name}' non reconnu.")

        return handler(**arguments)


calculator_service = CalculatorService()
