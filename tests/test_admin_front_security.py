"""Contrôles statiques de sécurité du back-office livré au navigateur."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_admin_ne_stocke_plus_le_jwt_dans_local_storage() -> None:
    source = (PROJECT_ROOT / "admin_web" / "app.js").read_text(encoding="utf-8")

    assert "localStorage.setItem('prosartisan_admin_token'" not in source
    assert "options.credentials = 'same-origin'" in source


def test_admin_n_affiche_plus_les_identifiants_de_demo() -> None:
    html = (PROJECT_ROOT / "admin_web" / "index.html").read_text(encoding="utf-8")

    assert "Remplir Démo" not in html
    assert "dev_admin_password" not in html
