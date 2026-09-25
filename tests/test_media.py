"""Tests du stockage des photos de chantier hors base et des URLs signées."""

import base64
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.schemas.conversation import MessageResponse
from app.services.chat_history_service import chat_history_service
from app.services.media_service import (
    MAX_IMAGE_BYTES,
    ImageInvalideError,
    media_service,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _data_url(content: bytes, mime: str = "png") -> str:
    return f"data:image/{mime};base64,{base64.b64encode(content).decode('ascii')}"


@pytest.fixture(autouse=True)
def _upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    return tmp_path


def _decouper(url: str) -> tuple[str, int, str]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    return parsed.path.rsplit("/", 1)[-1], int(qs["exp"][0]), qs["sig"][0]


# ── Validation ──


def test_photo_png_valide_stockee_sur_disque(_upload_dir):
    ref = media_service.store(media_service.prepare_chat_image(_data_url(PNG)))

    assert ref.startswith("media:") and ref.endswith(".png")
    assert (_upload_dir / "chat_images" / ref[len("media:") :]).read_bytes() == PNG


def test_url_distante_conservee_telle_quelle():
    url = "https://example.com/fissure.jpg"
    assert media_service.store(media_service.prepare_chat_image(url)) == url


@pytest.mark.parametrize(
    "image_url",
    [
        "data:image/svg+xml;base64,PHN2Zz4=",  # SVG : vecteur de script, refusé
        "data:image/png;base64,@@@",  # Base64 invalide
        _data_url(b"pas une image"),  # signature binaire absente
        _data_url(PNG, "jpeg"),  # type déclaré ≠ contenu
        "javascript:alert(1)",
    ],
)
def test_photos_invalides_refusees(image_url):
    with pytest.raises(ImageInvalideError):
        media_service.prepare_chat_image(image_url)


def test_photo_trop_volumineuse_refusee():
    with pytest.raises(ImageInvalideError, match="volumineuse"):
        media_service.prepare_chat_image(_data_url(PNG + b"\x00" * MAX_IMAGE_BYTES))


# ── URLs signées ──


def test_url_signee_valide(_upload_dir):
    ref = media_service.store(media_service.prepare_chat_image(_data_url(PNG)))
    name, exp, sig = _decouper(media_service.public_url(ref))

    assert media_service.resolve_signed(name, exp, sig) is not None


def test_url_signee_falsifiee_ou_expiree_refusee():
    ref = media_service.store(media_service.prepare_chat_image(_data_url(PNG)))
    name, exp, sig = _decouper(media_service.public_url(ref))

    assert media_service.resolve_signed(name, exp + 1, sig) is None  # exp modifié
    assert media_service.resolve_signed(name, exp, "0" * 64) is None
    _, exp_passe, sig_passe = _decouper(
        media_service.public_url(ref, now=time.time() - 7200)
    )
    assert media_service.resolve_signed(name, exp_passe, sig_passe) is None


def test_nom_de_fichier_hors_format_refuse():
    """Aucun nom arbitraire (traversée de chemin) n'est résolu, même bien signé."""
    exp = int(time.time()) + 60
    assert media_service.resolve_signed("../../etc/passwd", exp, "x") is None


@pytest.mark.asyncio
async def test_route_sert_la_photo_signee():
    ref = media_service.store(media_service.prepare_chat_image(_data_url(PNG)))
    url = media_service.public_url(ref)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.get(url)
        name, exp, _ = _decouper(url)
        refus = await client.get(
            f"/api/media/chat-images/{name}?exp={exp}&sig={'0' * 64}"
        )

    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/png"
    assert ok.content == PNG
    assert refus.status_code == 404


def test_historique_expose_une_url_signee():
    msg = MessageResponse(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="user",
        content="Fissure ?",
        image_url="media:" + "a" * 32 + ".png",
        created_at=datetime.now(UTC),
    )
    url = msg.model_dump()["image_url"]

    assert url.startswith("/api/media/chat-images/" + "a" * 32 + ".png?exp=")
    assert "sig=" in url


# ── Chat ──


@pytest.mark.asyncio
async def test_chat_enregistre_une_reference_et_non_le_base64(monkeypatch):
    enregistres = []

    async def _ajouter(**kwargs):
        enregistres.append(kwargs)

    monkeypatch.setattr(chat_history_service, "add_message_to_conversation", _ajouter)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={"question": "Cette fissure est grave ?", "image_url": _data_url(PNG)},
        )

    assert response.status_code == 200
    user_msg = next(m for m in enregistres if m["role"] == "user")
    assert user_msg["image_url"].startswith("media:")


@pytest.mark.asyncio
async def test_chat_photo_invalide_refusee_sans_consommer_de_quota(monkeypatch):
    from app.services.quota_service import quota_service

    appels = []

    async def _consume(**kwargs):
        appels.append(kwargs)
        return True

    monkeypatch.setattr(quota_service, "consume_quota", _consume)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={"question": "Et ça ?", "image_url": "data:image/svg+xml;base64,PA=="},
        )

    assert response.status_code == 422
    assert appels == []


@pytest.mark.asyncio
async def test_script_de_reprise_deplace_les_photos_base64(monkeypatch):
    """Les photos Base64 existantes deviennent des références ; l'illisible passe à NULL."""
    from unittest.mock import AsyncMock, MagicMock

    from app.scripts import migrate_chat_images as script

    valide = MagicMock(id=1, image_url=_data_url(PNG))
    illisible = MagicMock(id=2, image_url="data:image/png;base64,@@@")
    lots = iter([[valide, illisible], []])

    class _Session:
        commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt):
            return MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=lambda: next(lots)))
            )

    monkeypatch.setattr(script, "async_session", _Session)

    stats = await script.migrate_chat_images(batch_size=10)

    assert stats == {"migrees": 1, "invalides": 1}
    assert valide.image_url.startswith("media:")
    assert illisible.image_url is None
