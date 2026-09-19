"""Tests unitaires et d'intégration pour le service de calculateurs métiers et ses endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.calculator_service import CalculatorService, calculator_service

# ── 1. DOSAGE BÉTON & MORTIER ────────────────────────────────────────────────


def test_calculer_dosage_beton_volume_direct():
    """Vérifie le calcul de dosage béton à partir d'un volume en m³."""
    res = calculator_service.calculer_dosage_beton(
        volume_m3=2.0,
        type_ouvrage="poteau_poutre_dalle",
        classe_ciment="CPJ 42.5",
    )
    assert "resultats" in res
    r = res["resultats"]
    assert r["ciment_poids_kg"] == 700.0  # 350 kg/m³ * 2
    assert r["sacs_ciment_50kg"] == 14  # 700 / 50
    assert r["sable_litres"] == 800.0  # 400 L/m³ * 2
    assert r["gravier_litres"] == 1600.0  # 800 L/m³ * 2
    assert r["sable_brouettes_60l"] > 0
    assert r["gravier_brouettes_60l"] > 0
    assert len(res["conseils_chantier"]) > 0


def test_calculer_dosage_beton_dimensions():
    """Vérifie le calcul automatique du volume à partir des cotes longueur x largeur x épaisseur."""
    res = calculator_service.calculer_dosage_beton(
        longueur_m=4.0,
        largeur_m=3.0,
        epaisseur_m=0.15,  # dalle de 1.8 m³
        type_ouvrage="poteau_poutre_dalle",
    )
    assert res["volume_m3"] == 1.8
    assert res["resultats"]["sacs_ciment_50kg"] == 13  # 1.8 * 350 = 630 kg -> 13 sacs


def test_calculer_dosage_beton_mortier_pose():
    """Vérifie le dosage sans gravier pour mortier de pose."""
    res = calculator_service.calculer_dosage_beton(
        volume_m3=1.0,
        type_ouvrage="mortier_pose_parpaing",
    )
    assert res["resultats"]["gravier_litres"] == 0
    assert res["resultats"]["sable_litres"] == 1000.0
    assert res["resultats"]["sacs_ciment_50kg"] == 6  # 300 kg / 50


def test_calculer_dosage_beton_erreurs_arguments():
    """Vérifie les rejets pour paramètres invalides."""
    with pytest.raises(ValueError, match="volume_m3"):
        calculator_service.calculer_dosage_beton(volume_m3=None)

    with pytest.raises(ValueError, match="strictement supérieur"):
        calculator_service.calculer_dosage_beton(volume_m3=-1.0)


# ── 2. SECTION DE CÂBLE & PROTECTION ÉLECTRIQUE ─────────────────────────────


def test_calculer_section_cable_monophase():
    """Vérifie le dimensionnement d'un circuit prises/clim monophasé 3500W sur 25m."""
    res = calculator_service.calculer_section_cable(
        puissance_watts=3500,
        longueur_metres=25.0,
        tension_volts=230,
        type_alimentation="monophase",
        chute_tension_max_pct=3.0,
    )
    assert res["intensite_a"] > 16.0
    assert res["section_normalisee_recommandee_mm2"] in [2.5, 4.0, 6.0]
    assert res["disjoncteur_protection_recommande_a"] in [20, 25, 32]
    assert res["chute_tension_reelle_pct"] <= 3.0
    assert res["conformite_norme"] is True


def test_calculer_section_cable_triphase():
    """Vérifie le calcul en triphasé 400V pour un moteur de 15 kW."""
    res = calculator_service.calculer_section_cable(
        puissance_watts=15000,
        longueur_metres=40.0,
        tension_volts=400,
        type_alimentation="triphase",
        chute_tension_max_pct=5.0,
    )
    assert res["intensite_a"] > 0
    assert res["section_normalisee_recommandee_mm2"] >= 2.5
    assert res["disjoncteur_protection_recommande_a"] >= 25


def test_calculer_section_cable_forte_puissance_triphase():
    """Vérifie le calcul en triphasé pour une installation industrielle de 35 kW."""
    res = calculator_service.calculer_section_cable(
        puissance_watts=35000,
        longueur_metres=60.0,
        tension_volts=400,
        type_alimentation="triphase",
        chute_tension_max_pct=3.0,
    )
    assert res["intensite_a"] > 50.0
    assert res["section_normalisee_recommandee_mm2"] >= 10.0
    assert res["disjoncteur_protection_recommande_a"] >= 63


def test_calculer_section_cable_erreurs():
    """Vérifie les exceptions sur données invalides."""
    with pytest.raises(ValueError, match="puissance_watts"):
        calculator_service.calculer_section_cable(
            puissance_watts=0, intensite_amperes=None
        )


# ── 3. PLOMBERIE : ÉVACUATION & PENTE ────────────────────────────────────────


def test_calculer_evacuation_plomberie_wc():
    """Vérifie les préconisations WC (DN 100, pente 2%)."""
    res = calculator_service.calculer_evacuation_plomberie(
        type_appareil="wc",
        longueur_canalisation_m=5.0,
        pente_souhaitee_pct=2.0,
    )
    assert res["diametre_nominal_pvc_mm"] == 100
    assert res["pente_pct"] == 2.0
    assert res["denivele_requis_cm"] == 10.0  # 5m * 2 cm/m
    assert len(res["bonnes_pratiques"]) > 0


def test_calculer_evacuation_plomberie_evier():
    """Vérifie les préconisations évier de cuisine (DN 50)."""
    res = calculator_service.calculer_evacuation_plomberie(
        type_appareil="evier_cuisine",
        longueur_canalisation_m=3.0,
        pente_souhaitee_pct=2.5,
    )
    assert res["diametre_nominal_pvc_mm"] == 50
    assert res["denivele_requis_cm"] == 7.5


# ── 4. REVÊTEMENTS : CARRELAGE & PEINTURE ────────────────────────────────────


def test_calculer_carrelage_et_colle_pose_droite():
    """Vérifie le calcul de carrelage en pose droite (+10% chutes)."""
    res = calculator_service.calculer_carrelage_et_colle(
        surface_m2=50.0,
        format_carreau_cm="60x60",
        type_pose="droite",
    )
    assert res["surface_a_commander_m2"] == 55.0  # 50 + 10%
    assert res["mortier_colle"]["sacs_25kg"] == 12  # 50 * 6 = 300 kg -> 12 sacs
    assert res["mortier_joint"]["sacs_5kg"] == 4  # 50 * 0.4 = 20 kg -> 4 sacs


def test_calculer_carrelage_pose_diagonale():
    """Vérifie la marge de 15% pour pose en diagonale."""
    res = calculator_service.calculer_carrelage_et_colle(
        surface_m2=20.0,
        type_pose="diagonale",
    )
    assert res["surface_a_commander_m2"] == 23.0  # 20 + 15%


# ── 5. CLIMATISATION : BILAN THERMIQUE ──────────────────────────────────────


def test_calculer_bilan_climatisation():
    """Vérifie la recommandation d'un Split pour une chambre de 25m²."""
    res = calculator_service.calculer_bilan_climatisation(
        surface_m2=25.0,
        hauteur_plafond_m=2.8,
        type_toiture="dalle_beton",
        exposition_soleil="moyenne",
    )
    assert res["volume_m3"] == 70.0
    assert res["besoin_calcule_btu"] > 10000
    assert res["puissance_cv"] in [1.5, 2.0]
    assert "Split" in res["modele_recommande"]


# ── 6. DISPATCHER & TOOL DEFINITIONS ─────────────────────────────────────────


def test_execute_tool_valide():
    """Vérifie l'exécution d'un outil via son nom et arguments JSON."""
    res = CalculatorService.execute_tool(
        "calculer_dosage_beton",
        {"volume_m3": 1.0, "type_ouvrage": "beton_proprete"},
    )
    assert res["resultats"]["ciment_poids_kg"] == 250.0


def test_execute_tool_inconnu_leve_erreur():
    """Vérifie le rejet d'un nom d'outil inexistant."""
    with pytest.raises(ValueError, match="non reconnu"):
        CalculatorService.execute_tool("calculer_vitesse_fusee", {})


def test_get_tool_definitions_structure():
    """Vérifie la conformité de la spécification JSON Schema pour Mistral."""
    tools = CalculatorService.get_tool_definitions()
    assert len(tools) == 5
    for t in tools:
        assert t["type"] == "function"
        assert "name" in t["function"]
        assert "description" in t["function"]
        assert "parameters" in t["function"]


# ── 7. ENDPOINTS FASTAPI ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoint_list_calculators():
    """GET /api/chat/calculators retourne la liste des outils."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/chat/calculators")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    tool_names = [item["name"] for item in data]
    assert "calculer_dosage_beton" in tool_names
    assert "calculer_section_cable" in tool_names


@pytest.mark.asyncio
async def test_endpoint_calculate_success():
    """POST /api/chat/calculate exécute un calcul avec succès."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "tool_name": "calculer_dosage_beton",
            "arguments": {
                "volume_m3": 3.0,
                "type_ouvrage": "poteau_poutre_dalle",
            },
        }
        response = await client.post("/api/chat/calculate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["tool_name"] == "calculer_dosage_beton"
    assert data["result"]["resultats"]["ciment_poids_kg"] == 1050.0


@pytest.mark.asyncio
async def test_endpoint_calculate_bad_request():
    """POST /api/chat/calculate renvoie 400 si paramètres invalides."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "tool_name": "calculer_dosage_beton",
            "arguments": {"volume_m3": -5.0},
        }
        response = await client.post("/api/chat/calculate", json=payload)

    assert response.status_code == 400
    assert "strictement supérieur" in response.json()["detail"]


@pytest.mark.asyncio
async def test_endpoint_calculate_unknown_tool():
    """POST /api/chat/calculate renvoie 400 si l'outil n'existe pas."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "tool_name": "calculateur_inconnu",
            "arguments": {},
        }
        response = await client.post("/api/chat/calculate", json=payload)

    assert response.status_code == 400
    assert "non reconnu" in response.json()["detail"]
