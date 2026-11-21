"""Devis sans prix inventés : grille de prix de référence et extraction IA.

Régressions couvertes (analyse du 2026-11-21) :
- le LLM fixait les prix « du marché d'Abidjan » sans source ;
- en cas d'échec de tous les fournisseurs IA, le service renvoyait un devis
  factice aux prix codés en dur (6 000 F, 28 000 F…) présenté comme réel ;
- les quantités de matériaux étaient estimées par le LLM au lieu des
  calculateurs certifiés ;
- le total de ligne était tronqué au lieu d'être arrondi.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.audit_log import AuditLog
from app.models.prix_reference import PrixReference
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.quote import PRIX_A_SAISIR, PRIX_GRILLE
from app.services import quote_service as quote_module
from app.services.llm_provider_service import (
    FournisseursIAIndisponiblesError,
    llm_provider_service,
)
from app.services.prix_reference_service import (
    choisir_prix,
    mots_significatifs,
    normaliser_unite,
    prix_reference_service,
)
from app.services.quote_service import DevisIndisponibleError, quote_service
from tests.conftest import mock_get_db


def _prix(
    id_: int,
    designation: str,
    unite: str,
    prix: int,
    *,
    commune: str | None = None,
    mots_cles: str | None = None,
    actif: bool = True,
    releve: date = date(2026, 11, 1),
) -> PrixReference:
    return PrixReference(
        id=id_,
        designation=designation,
        unite=unite,
        prix_unitaire=prix,
        type_item="FOURNITURE",
        mots_cles=mots_cles,
        commune=commune,
        date_releve=releve,
        is_active=actif,
    )


GRILLE = [
    _prix(1, "Ciment CPJ 42.5", "sac", 5200),
    _prix(2, "Ciment CPJ 42.5", "sac", 5500, commune="Yopougon"),
    _prix(3, "Sable de lagune", "m3", 9000, mots_cles="sable lavé, sable"),
    _prix(4, "Gravier concassé 15/25", "m3", 15000, mots_cles="gravier"),
    _prix(5, "Agglo creux 15", "unite", 350, mots_cles="parpaing 15"),
    _prix(6, "Disjoncteur divisionnaire 20A", "unite", 4500),
    _prix(7, "Ciment CPJ 42.5", "sac", 6000, commune="Bouaké"),
    _prix(8, "Peinture glycéro", "litre", 3000, actif=False),
]


# ── Correspondance ligne ↔ grille ────────────────────────────────────────


def test_normalisation_des_unites() -> None:
    assert normaliser_unite("sacs") == "sac"
    assert normaliser_unite("m³") == "m3"
    assert normaliser_unite("U") == "unite"
    assert normaliser_unite("unité") == "unite"
    assert normaliser_unite("barre 4m") == "barre"


def test_mots_significatifs_gardent_les_nombres() -> None:
    assert {"ciment", "cpj", "42.5"} <= mots_significatifs("Ciment CPJ 42,5")
    assert "sac" in mots_significatifs("sacs")


def test_prix_sans_commune_applique_par_defaut() -> None:
    prix = choisir_prix("Ciment CPJ 42.5 (sac de 50 kg)", "sac", None, GRILLE)
    assert prix is not None and prix.prix_reference_id == 1


def test_prix_de_la_commune_du_chantier_prioritaire() -> None:
    prix = choisir_prix("Ciment CPJ 42.5", "sacs", "yopougon", GRILLE)
    assert prix is not None and prix.prix_unitaire == 5500


def test_prix_d_une_autre_commune_jamais_applique() -> None:
    grille = [_prix(7, "Ciment CPJ 42.5", "sac", 6000, commune="Bouaké")]
    assert choisir_prix("Ciment CPJ 42.5", "sac", "Cocody", grille) is None


def test_classe_de_ciment_differente_sans_prix() -> None:
    """Les nombres d'une référence doivent tous figurer dans la ligne."""
    assert choisir_prix("Ciment CPJ 32.5", "sac", None, GRILLE) is None


def test_unite_differente_sans_prix() -> None:
    assert choisir_prix("Ciment CPJ 42.5", "kg", None, GRILLE) is None


def test_synonyme_de_la_grille() -> None:
    prix = choisir_prix("Parpaing 15 cm", "unité", None, GRILLE)
    assert prix is not None and prix.prix_reference_id == 5


def test_prix_inactif_ignore() -> None:
    assert choisir_prix("Peinture glycéro", "litre", None, GRILLE) is None


def test_designation_sans_rapport_sans_prix() -> None:
    assert choisir_prix("Main d'œuvre maçon", "jour", None, GRILLE) is None


def test_releve_le_plus_recent_a_egalite() -> None:
    grille = [
        _prix(1, "Sable", "m3", 8000, releve=date(2026, 1, 1)),
        _prix(2, "Sable", "m3", 9500, releve=date(2026, 10, 1)),
    ]
    prix = choisir_prix("Sable", "m3", None, grille)
    assert prix is not None and prix.prix_unitaire == 9500


# ── Extraction IA ────────────────────────────────────────────────────────


@pytest.fixture
def ia_configuree(monkeypatch: pytest.MonkeyPatch):
    """Simule un fournisseur IA configuré dont la réponse est pilotée par le test."""
    monkeypatch.setattr(settings, "mistral_api_key", "cle-mistral-test")
    reponse = AsyncMock()
    monkeypatch.setattr(llm_provider_service, "complete_text_with_failover", reponse)

    async def _grille(_db, _metier_id):
        return GRILLE

    monkeypatch.setattr(prix_reference_service, "grille_pour_devis", _grille)
    return reponse


@pytest.mark.asyncio
async def test_prix_du_llm_ignores_et_remplaces_par_la_grille(ia_configuree) -> None:
    ia_configuree.return_value = json.dumps(
        {
            "titre": "Pose de disjoncteurs",
            "client_adresse": "Cocody",
            "items": [
                {
                    "description": "Disjoncteur divisionnaire 20A",
                    "quantite": 3,
                    "unite": "unité",
                    "prix_unitaire": 99000,
                    "type_item": "FOURNITURE",
                },
                {
                    "description": "Pose et raccordement",
                    "quantite": 1,
                    "unite": "forfait",
                    "prix_unitaire": 50000,
                    "type_item": "MAIN_D_OEUVRE",
                },
            ],
        }
    )
    res = await quote_service.extract_quote_from_text(
        description_brute="3 disjoncteurs 20A à poser chez Koffi", db=MagicMock()
    )

    disj, pose = res.items
    assert disj.prix_unitaire == 4500 and disj.prix_source == PRIX_GRILLE
    assert disj.prix_reference_id == 6
    assert disj.total == 13500
    assert pose.prix_unitaire == 0 and pose.prix_source == PRIX_A_SAISIR
    assert res.lignes_sans_prix == 1
    assert any("prix à saisir" in a for a in res.avertissements)
    assert res.mode_demonstration is False


@pytest.mark.asyncio
async def test_prix_dicte_par_l_artisan_repris_seulement_s_il_est_ecrit(
    ia_configuree,
) -> None:
    ia_configuree.return_value = json.dumps(
        {
            "items": [
                {
                    "description": "Receveur de douche 90x90",
                    "quantite": 1,
                    "unite": "unité",
                    "prix_cite": 75000,
                },
                {
                    "description": "Disjoncteur divisionnaire 20A",
                    "quantite": 2,
                    "unite": "unité",
                    "prix_cite": 8000,  # absent de la description : inventé
                },
                {
                    "description": "Pose et plomberie",
                    "quantite": 1,
                    "unite": "forfait",
                    "prix_cite": "60000",
                },
            ]
        }
    )
    res = await quote_service.extract_quote_from_text(
        description_brute=(
            "Receveur 90x90 à 75 000 F, 2 disjoncteurs 20A, pose et plomberie à 60.000 F"
        ),
        db=MagicMock(),
    )
    receveur, disj, pose = res.items
    assert (receveur.prix_unitaire, receveur.prix_source) == (75000, "artisan")
    # Prix « cité » introuvable dans la description : grille, pas l'IA
    assert (disj.prix_unitaire, disj.prix_source) == (4500, PRIX_GRILLE)
    assert (pose.prix_unitaire, pose.prix_source) == (60000, "artisan")


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (75000, 75000),
        (75000.0, 75000),
        (750, None),
        (-5, None),
        (True, None),
        ("x", None),
    ],
)
def test_verification_du_prix_cite(valeur, attendu) -> None:
    assert (
        quote_service._prix_cite_verifie(valeur, "Receveur à 75 000 F et 1 750,5 m")
        == attendu
    )


@pytest.mark.asyncio
async def test_quantites_de_materiaux_issues_des_calculateurs(ia_configuree) -> None:
    ia_configuree.return_value = json.dumps(
        {
            "titre": "Mur de clôture",
            "items": [
                {
                    "description": "Main d'œuvre maçon",
                    "quantite": 4,
                    "unite": "jour",
                    "type_item": "MAIN_D_OEUVRE",
                }
            ],
            "calculs": [
                {
                    "outil": "calculer_agglos_mur",
                    "arguments": {
                        "longueur_m": 10,
                        "hauteur_m": 3,
                        "surface_ouvertures_m2": 2,
                        "epaisseur_agglo_cm": 15,
                    },
                },
                {"outil": "calculer_dosage_beton", "arguments": {"volume_m3": 1}},
                {"outil": "calculer_section_cable", "arguments": {}},
            ],
        }
    )
    res = await quote_service.extract_quote_from_text(
        description_brute="Mur 10 m sur 3 m en agglos de 15", db=MagicMock()
    )
    par_designation = {it.description: it for it in res.items}

    agglos = par_designation["Agglo creux 15 cm (40x20)"]
    assert agglos.quantite == 368 and agglos.quantite_source == "calculateur"
    assert agglos.prix_unitaire == 350  # synonyme / désignation de la grille
    # Ciment du mur (4 sacs) + béton de 1 m³ (7 sacs), fusionnés
    ciment = par_designation["Ciment CPJ 42.5 (sac de 50 kg)"]
    assert ciment.quantite == 11 and ciment.prix_unitaire == 5200
    assert par_designation["Gravier"].prix_unitaire == 15000
    assert par_designation["Main d'œuvre maçon"].quantite_source == "ia"
    assert any("calculer_section_cable" in a for a in res.avertissements)


@pytest.mark.asyncio
async def test_calcul_invalide_signale_sans_planter(ia_configuree) -> None:
    ia_configuree.return_value = json.dumps(
        {
            "items": [],
            "calculs": [
                {
                    "outil": "calculer_dosage_beton",
                    "arguments": {"volume_m3": 1, "type_ouvrage": "inconnu"},
                }
            ],
        }
    )
    res = await quote_service.extract_quote_from_text(
        description_brute="Béton pour une dalle", db=MagicMock()
    )
    assert res.items == []
    assert any("impossible" in a for a in res.avertissements)


@pytest.mark.asyncio
async def test_lignes_invalides_ignorees_et_total_arrondi(ia_configuree) -> None:
    ia_configuree.return_value = json.dumps(
        {
            "items": [
                {"description": "Sable", "quantite": 0.333, "unite": "m3"},
                {"description": "Ligne vide", "quantite": 0, "unite": "u"},
                {"description": "", "quantite": 2, "unite": "u"},
            ]
        }
    )
    res = await quote_service.extract_quote_from_text(
        description_brute="Un peu de sable", db=MagicMock()
    )
    assert len(res.items) == 1
    # 0,333 × 9 000 = 2 997 (arrondi, plus de troncature)
    assert res.items[0].total == 2997
    assert any("ignorée" in a for a in res.avertissements)


@pytest.mark.asyncio
async def test_ia_indisponible_jamais_de_devis_factice(ia_configuree) -> None:
    ia_configuree.side_effect = FournisseursIAIndisponiblesError("tout en panne")
    with pytest.raises(DevisIndisponibleError):
        await quote_service.extract_quote_from_text(
            description_brute="Changement de 3 disjoncteurs", db=MagicMock()
        )


@pytest.mark.asyncio
async def test_reponse_ia_illisible_jamais_de_devis_factice(ia_configuree) -> None:
    ia_configuree.return_value = "Voici votre devis : 3 disjoncteurs à 6000 F"
    with pytest.raises(DevisIndisponibleError):
        await quote_service.extract_quote_from_text(
            description_brute="Changement de 3 disjoncteurs", db=MagicMock()
        )


@pytest.mark.asyncio
async def test_mode_demo_sans_aucun_prix_code_en_dur() -> None:
    res = await quote_service.extract_quote_from_text(
        description_brute="J'ai posé 3 disjoncteurs et 40m de câble pour Koffi"
    )
    assert res.mode_demonstration is True
    assert res.avertissements[0].startswith("Mode démonstration")
    assert all(it.prix_unitaire == 0 for it in res.items)
    assert all(it.prix_source == PRIX_A_SAISIR for it in res.items)


@pytest.mark.asyncio
async def test_mode_demo_interdit_en_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(DevisIndisponibleError):
        await quote_service.extract_quote_from_text(
            description_brute="Changement de 3 disjoncteurs"
        )


@pytest.mark.asyncio
async def test_bascule_texte_leve_si_tous_les_fournisseurs_echouent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "mistral_api_key", "cle-mistral-test")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-cle-gemini-test")
    await llm_provider_service.reset_health()

    mistral_chat = MagicMock()
    mistral_chat.complete_async = AsyncMock(side_effect=RuntimeError("Mistral 500"))
    monkeypatch.setattr(
        llm_provider_service,
        "_http_transport",
        httpx.MockTransport(lambda _req: httpx.Response(503, text="indisponible")),
    )

    with pytest.raises(FournisseursIAIndisponiblesError):
        await llm_provider_service.complete_text_with_failover(
            messages=[{"role": "user", "content": "x"}],
            mistral_client=SimpleNamespace(chat=mistral_chat),
        )
    await llm_provider_service.reset_health()


# ── Route /api/quotes/extract ────────────────────────────────────────────


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = create_access_token({"sub": str(uuid.uuid4()), "role": "artisan"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_route_extract_503_si_ia_indisponible(monkeypatch, auth_headers) -> None:
    async def _panne(**_kwargs):
        raise DevisIndisponibleError("panne")

    monkeypatch.setattr(quote_module.quote_service, "extract_quote_from_text", _panne)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/quotes/extract",
            json={"description_brute": "Changement de 3 disjoncteurs"},
            headers=auth_headers,
        )
    assert res.status_code == 503
    assert "saisissez les lignes" in res.json()["detail"]


@pytest.mark.asyncio
async def test_route_extract_borne_la_taille_de_la_description(auth_headers) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/quotes/extract",
            json={"description_brute": "x" * 4001},
            headers=auth_headers,
        )
    assert res.status_code == 422


# ── Routes admin de la grille ────────────────────────────────────────────


def _admin_db(user: User, *responses, captured: list | None = None):
    async def _db():
        session = MagicMock()
        queue = [("scalar", user), *responses]

        async def _execute(_stmt):
            kind, value = queue.pop(0)
            res = MagicMock()
            res.scalar_one_or_none.return_value = value
            res.scalars.return_value.all.return_value = value if kind == "rows" else []
            return res

        def _add(obj):
            if captured is not None:
                captured.append(obj)

        async def _refresh(obj):
            if getattr(obj, "id", None) is None:
                obj.id = 42

        session.execute = _execute
        session.add = _add
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.delete = AsyncMock()
        session.refresh = _refresh
        yield session

    return _db


@pytest.fixture
def admin_restreint() -> User:
    role = Role(id=uuid.uuid4(), code="lecteur_prix", label="Lecteur prix")
    role.permissions = [Permission(id=uuid.uuid4(), code="prix.read")]
    user = User(id=uuid.uuid4(), email="lecteur@prosartisan.ci", is_admin=True)
    user.role = role
    return user


@pytest.fixture
def admin_historique() -> User:
    return User(
        id=uuid.uuid4(), email="admin@prosartisan.ci", is_admin=True, role_id=None
    )


_PAYLOAD = {
    "designation": "Ciment CPJ 42.5",
    "unite": "sac",
    "prix_unitaire": 5200,
    "commune": "Yopougon",
    "source": "Relevé quincaillerie, novembre 2026",
}


@pytest.mark.asyncio
async def test_creation_prix_exige_prix_write(admin_restreint) -> None:
    app.dependency_overrides[get_db] = _admin_db(admin_restreint)
    token = create_access_token({"sub": str(admin_restreint.id)})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/admin/parametres/prix-references",
                json=_PAYLOAD,
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_creation_prix_auditee(admin_historique) -> None:
    ajoutes: list = []
    app.dependency_overrides[get_db] = _admin_db(admin_historique, captured=ajoutes)
    token = create_access_token({"sub": str(admin_historique.id)})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/admin/parametres/prix-references",
                json=_PAYLOAD,
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["prix_unitaire"] == 5200 and data["type_item"] == "FOURNITURE"
        audits = [o for o in ajoutes if isinstance(o, AuditLog)]
        assert audits and audits[0].action == "parametres.prix_reference.create"
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_creation_prix_refuse_un_montant_negatif(admin_historique) -> None:
    app.dependency_overrides[get_db] = _admin_db(admin_historique)
    token = create_access_token({"sub": str(admin_historique.id)})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/admin/parametres/prix-references",
                json={**_PAYLOAD, "prix_unitaire": -5, "type_item": "GRATUIT"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 422
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_lecture_grille_avec_prix_read(admin_restreint) -> None:
    app.dependency_overrides[get_db] = _admin_db(admin_restreint, ("rows", GRILLE[:2]))
    token = create_access_token({"sub": str(admin_restreint.id)})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get(
                "/api/admin/parametres/prix-references",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 200, res.text
        assert [p["id"] for p in res.json()] == [1, 2]
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_suppression_prix_inconnu_404(admin_historique) -> None:
    app.dependency_overrides[get_db] = _admin_db(admin_historique, ("scalar", None))
    token = create_access_token({"sub": str(admin_historique.id)})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.delete(
                "/api/admin/parametres/prix-references/999",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 404
    finally:
        app.dependency_overrides[get_db] = mock_get_db
