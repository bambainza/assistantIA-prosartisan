"""Contrôles statiques de sécurité du back-office livré au navigateur."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_admin_ne_stocke_plus_le_jwt_dans_local_storage() -> None:
    source = "\n".join(
        f.read_text(encoding="utf-8")
        for f in sorted((PROJECT_ROOT / "admin_web" / "js").glob("*.js"))
    )

    assert "localStorage.setItem('prosartisan_admin_token'" not in source
    assert "options.credentials = 'same-origin'" in source


def test_admin_n_affiche_plus_les_identifiants_de_demo() -> None:
    html = (PROJECT_ROOT / "admin_web" / "index.html").read_text(encoding="utf-8")

    assert "Remplir Démo" not in html
    assert "dev_admin_password" not in html


def test_admin_charge_tous_les_scripts_du_back_office_dans_l_ordre() -> None:
    """index.html charge chaque script de admin_web/js/, core.js en premier."""
    html = (PROJECT_ROOT / "admin_web" / "index.html").read_text(encoding="utf-8")
    scripts = sorted(p.name for p in (PROJECT_ROOT / "admin_web" / "js").glob("*.js"))

    for nom in scripts:
        assert f'<script src="/admin/js/{nom}"></script>' in html
    assert html.index("/admin/js/core.js") < min(
        html.index(f"/admin/js/{nom}") for nom in scripts if nom != "core.js"
    )
    assert '<script src="/admin/app.js">' not in html
