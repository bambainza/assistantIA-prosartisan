"""Régressions statiques pour la surface Web du chat."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_chat_ne_stocke_aucun_jwt_dans_local_storage() -> None:
    source = (PROJECT_ROOT / "chat_web" / "app.js").read_text(encoding="utf-8")

    assert "localStorage.setItem('prosartisan_token'" not in source
    assert "localStorage.setItem('prosartisan_refresh_token'" not in source
    assert "/api/auth/web/login" in source
    assert "/api/auth/web/google" in source


def test_tout_rendu_markdown_passe_par_l_assainissement() -> None:
    source = (PROJECT_ROOT / "chat_web" / "app.js").read_text(encoding="utf-8")

    assert "return sanitizeRenderedHtml(parsedHtml)" in source
    assert "innerHTML = marked.parse" not in source
    assert "allowedTags" in source
    assert "['http:', 'https:', 'mailto:'].includes(parsed.protocol)" in source


def test_actions_de_message_ne_contiennent_plus_de_javascript_inline() -> None:
    source = (PROJECT_ROOT / "chat_web" / "app.js").read_text(encoding="utf-8")

    assert "escapedContent" not in source
    assert "escapedResponse" not in source
    assert 'onclick="copyMessageText' not in source
    assert "appendMessageActions" in source


def test_handlers_html_herites_sont_tous_migres_vers_add_event_listener() -> None:
    html = (PROJECT_ROOT / "chat_web" / "index.html").read_text(encoding="utf-8")
    source = (PROJECT_ROOT / "chat_web" / "app.js").read_text(encoding="utf-8")
    handler_names = set(re.findall(r'on(?:click|input)="([A-Za-z_$][\w$]*)\(', html))

    assert handler_names
    assert all(f"'{name}'" in source for name in handler_names)
    assert "migrateTrustedInlineHandlers();" in source
