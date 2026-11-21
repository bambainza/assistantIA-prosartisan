"""Régressions de sécurité des calculateurs certifiés.

- Table câbles alignée sur l'habitat NF C 15-100 : l'ancienne table associait
  2,5 mm² à 25 A et 6 mm² à 40 A (risque d'échauffement des conducteurs).
- Dosage béton : un type d'ouvrage inconnu ne bascule plus en silence sur le
  béton de structure ; la classe de ciment agit sur le dosage.
- Nouveaux outils : agglos d'un mur, conversions d'unités de chantier.
"""

from __future__ import annotations

import pytest

from app.services.calculator_service import (
    CALIBRE_MAX_DISJONCTEUR_ALUMINIUM_A,
    CALIBRE_MAX_DISJONCTEUR_CUIVRE_A,
    calculator_service,
)

# ── Électricité ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("intensite", "section_attendue", "disjoncteur_attendu"),
    [
        (10, 1.5, 10),
        (16, 1.5, 16),
        (18, 2.5, 20),
        (24, 4.0, 25),  # ancienne table : 2,5 mm² protégé par 25 A
        (30, 6.0, 32),
        (38, 10.0, 40),  # ancienne table : 6 mm² protégé par 40 A
        (60, 16.0, 63),  # ancienne table : 10 mm² protégé par 63 A
    ],
)
def test_section_cable_table_habitat(
    intensite: float, section_attendue: float, disjoncteur_attendu: int
) -> None:
    res = calculator_service.calculer_section_cable(
        intensite_amperes=intensite, longueur_metres=5
    )
    assert res["section_normalisee_recommandee_mm2"] == section_attendue
    assert res["disjoncteur_protection_recommande_a"] == disjoncteur_attendu


def test_table_cuivre_valeurs_usuelles_du_logement() -> None:
    assert CALIBRE_MAX_DISJONCTEUR_CUIVRE_A[1.5] == 16
    assert CALIBRE_MAX_DISJONCTEUR_CUIVRE_A[2.5] == 20
    assert CALIBRE_MAX_DISJONCTEUR_CUIVRE_A[6.0] == 32


@pytest.mark.parametrize("intensite", [1, 9.5, 17, 22, 27, 35, 45, 70, 90, 120, 150])
@pytest.mark.parametrize("nature", ["cuivre", "aluminium"])
def test_coordination_disjoncteur_section_toujours_respectee(
    intensite: float, nature: str
) -> None:
    """Invariant Ib ≤ In ≤ calibre max de la section retenue."""
    res = calculator_service.calculer_section_cable(
        intensite_amperes=intensite, longueur_metres=10, nature_conducteur=nature
    )
    table = (
        CALIBRE_MAX_DISJONCTEUR_CUIVRE_A
        if nature == "cuivre"
        else CALIBRE_MAX_DISJONCTEUR_ALUMINIUM_A
    )
    section = res["section_normalisee_recommandee_mm2"]
    disjoncteur = res["disjoncteur_protection_recommande_a"]
    assert intensite <= disjoncteur <= table[section]
    assert res["nature_conducteur"] == nature
    assert "hypotheses" in res


def test_aluminium_section_minimale_16() -> None:
    res = calculator_service.calculer_section_cable(
        intensite_amperes=10, longueur_metres=5, nature_conducteur="aluminium"
    )
    assert res["section_normalisee_recommandee_mm2"] >= 16.0


def test_intensite_hors_domaine_refusee() -> None:
    """Plus de section « par défaut » sous-dimensionnée au-delà de la table."""
    with pytest.raises(ValueError, match="hors du domaine"):
        calculator_service.calculer_section_cable(intensite_amperes=250)


def test_chute_de_tension_impossible_refusee() -> None:
    with pytest.raises(ValueError, match="Aucune section normalisée"):
        calculator_service.calculer_section_cable(
            intensite_amperes=60, longueur_metres=2000
        )


def test_nature_conducteur_inconnue_refusee() -> None:
    with pytest.raises(ValueError, match="nature_conducteur"):
        calculator_service.calculer_section_cable(
            intensite_amperes=10, nature_conducteur="or"
        )


# ── Béton ────────────────────────────────────────────────────────────────


def test_type_ouvrage_inconnu_refuse() -> None:
    with pytest.raises(ValueError, match="type_ouvrage 'dalle_magique' inconnu"):
        calculator_service.calculer_dosage_beton(
            volume_m3=1, type_ouvrage="dalle_magique"
        )


def test_classe_ciment_inconnue_refusee() -> None:
    with pytest.raises(ValueError, match="classe_ciment"):
        calculator_service.calculer_dosage_beton(volume_m3=1, classe_ciment="CEM X")


def test_cpj_32_5_augmente_le_dosage_des_ouvrages_porteurs() -> None:
    r42 = calculator_service.calculer_dosage_beton(
        volume_m3=1, type_ouvrage="poteau_poutre_dalle", classe_ciment="CPJ 42.5"
    )
    r32 = calculator_service.calculer_dosage_beton(
        volume_m3=1, type_ouvrage="poteau_poutre_dalle", classe_ciment="CPJ 32.5"
    )
    assert r42["resultats"]["sacs_ciment_50kg"] == 7
    assert r32["resultats"]["sacs_ciment_50kg"] == 8
    assert r32["dosage_ciment_kg_m3"] == 400
    assert r32["ajustement_classe_ciment_kg_m3"] == 50


def test_cpj_32_5_sans_effet_sur_un_mortier() -> None:
    r42 = calculator_service.calculer_dosage_beton(
        volume_m3=1, type_ouvrage="mortier_pose_parpaing", classe_ciment="CPJ 42.5"
    )
    r32 = calculator_service.calculer_dosage_beton(
        volume_m3=1, type_ouvrage="mortier_pose_parpaing", classe_ciment="CPJ 32.5"
    )
    assert r42["resultats"] == r32["resultats"]


def test_alias_calculer_materiaux_btp() -> None:
    res = calculator_service.execute_tool("calculer_materiaux_btp", {"volume_m3": 2})
    assert res["resultats"]["sacs_ciment_50kg"] == 14


def test_parametre_inconnu_devient_erreur_de_saisie() -> None:
    with pytest.raises(ValueError, match="Paramètres invalides"):
        calculator_service.execute_tool(
            "calculer_dosage_beton", {"volume_m3": 1, "couleur": "rouge"}
        )


# ── Agglos ───────────────────────────────────────────────────────────────


def test_agglos_mur_avec_ouvertures_et_pertes() -> None:
    res = calculator_service.calculer_agglos_mur(
        longueur_m=10, hauteur_m=3, surface_ouvertures_m2=2, epaisseur_agglo_cm=15
    )
    assert res["surface_nette_m2"] == 28
    # 28 m² × 12,5 agglos/m² = 350, + 5 % de pertes = 367,5 → 368
    assert res["resultats"]["agglos_unites"] == 368
    # 28 m² × 0,018 m³/m² = 0,504 m³ de mortier à 300 kg/m³ → 151,2 kg → 4 sacs
    assert res["resultats"]["sacs_ciment_50kg"] == 4
    assert res["resultats"]["sable_m3"] == 0.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"longueur_m": 0, "hauteur_m": 2},
        {"longueur_m": 2, "hauteur_m": 2, "epaisseur_agglo_cm": 12},
        {"longueur_m": 2, "hauteur_m": 2, "surface_ouvertures_m2": 5},
        {"longueur_m": 2, "hauteur_m": 2, "pertes_pct": 40},
    ],
)
def test_agglos_mur_entrees_invalides(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        calculator_service.calculer_agglos_mur(**kwargs)


# ── Conversions ──────────────────────────────────────────────────────────


def test_conversion_volume_simple() -> None:
    res = calculator_service.convertir_unites_chantier(1, "m3", "brouette")
    assert res["resultat"] == pytest.approx(16.667, abs=0.001)
    res = calculator_service.convertir_unites_chantier(3, "seaux", "litres")
    assert res["resultat"] == 30


def test_conversion_sacs_de_ciment_en_brouettes() -> None:
    # 2 sacs = 100 kg ; 100 / 1,4 kg/L = 71,4 L ; / 60 L = 1,19 brouette
    res = calculator_service.convertir_unites_chantier(
        2, "sac", "brouette", materiau="ciment"
    )
    assert res["resultat"] == pytest.approx(1.19, abs=0.01)


def test_conversion_volume_masse_exige_le_materiau() -> None:
    with pytest.raises(ValueError, match="exige le matériau"):
        calculator_service.convertir_unites_chantier(1, "m3", "kg")


def test_conversion_sac_reserve_au_ciment() -> None:
    with pytest.raises(ValueError, match="sac de ciment"):
        calculator_service.convertir_unites_chantier(1, "sac", "kg", materiau="sable")


def test_conversion_unite_inconnue() -> None:
    with pytest.raises(ValueError, match="inconnue"):
        calculator_service.convertir_unites_chantier(1, "charrette", "m3")
