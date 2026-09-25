"""
Service Médias : stockage des photos de chantier hors de la base de données.

Une photo envoyée en Base64 (`data:image/...;base64,...`) pèse plusieurs Mo :
stockée telle quelle dans `messages.image_url`, elle alourdissait chaque
lecture d'historique. Elle est désormais validée (type, signature binaire,
taille), écrite dans `UPLOAD_DIR/chat_images/`, et la base ne conserve qu'une
référence courte `media:<nom>`.

Les clients reçoivent une URL signée HMAC à durée limitée
(`/api/media/chat-images/<nom>?exp=...&sig=...`) : une balise `<img>` ne
peut pas envoyer d'en-tête `Authorization`, la signature sert donc
d'autorisation. Elle n'est délivrée qu'au propriétaire de la discussion (les
routes d'historique filtrent par `user_id`).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

MEDIA_REF_PREFIX = "media:"
MAX_IMAGE_BYTES = 7 * 1024 * 1024
SIGNED_URL_TTL_SECONDS = 3600
CHAT_IMAGES_ROUTE = "/api/media/chat-images"

_DATA_URL_RE = re.compile(
    r"^data:image/(?P<mime>png|jpeg|jpg|webp|gif);base64,(?P<data>.+)$",
    re.DOTALL,
)
_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|webp|gif)$")

# Signatures binaires : le type déclaré dans l'URL ne suffit pas.
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "webp": (b"RIFF",),
}


class ImageInvalideError(ValueError):
    """Photo refusée (format non supporté, contenu corrompu ou trop volumineuse)."""


@dataclass(frozen=True)
class PreparedImage:
    """Photo validée, prête à être enregistrée (ou URL distante conservée telle quelle)."""

    content: bytes | None = None
    extension: str | None = None
    remote_url: str | None = None


def _chat_images_dir() -> Path:
    return Path(settings.upload_dir) / "chat_images"


def _signature(name: str, exp: int) -> str:
    key = settings.app_secret_key.encode("utf-8")
    return hmac.new(key, f"{name}:{exp}".encode(), hashlib.sha256).hexdigest()


class MediaService:
    """Validation, stockage et URLs signées des photos de chantier."""

    def prepare_chat_image(self, image_url: str | None) -> PreparedImage | None:
        """Valide la photo d'une question, sans rien écrire sur disque.

        Appelé avant la consommation du quota : une photo invalide ne doit
        coûter ni question ni appel au modèle de vision.
        """
        if not image_url:
            return None
        if image_url.startswith(("https://", "http://")):
            return PreparedImage(remote_url=image_url)

        match = _DATA_URL_RE.match(image_url)
        if not match:
            raise ImageInvalideError(
                "Format de photo non supporté (PNG, JPEG, WebP ou GIF attendu ; "
                "HEIC non pris en charge, convertissez la photo en JPEG)."
            )
        extension = "jpg" if match["mime"] in ("jpeg", "jpg") else match["mime"]
        try:
            content = base64.b64decode(match["data"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageInvalideError("Photo corrompue (Base64 invalide).") from exc

        if len(content) > MAX_IMAGE_BYTES:
            raise ImageInvalideError("Photo trop volumineuse (7 Mo maximum).")
        if not content.startswith(_MAGIC_BYTES[extension]) or (
            extension == "webp" and content[8:12] != b"WEBP"
        ):
            raise ImageInvalideError("Le contenu ne correspond pas à une image.")
        return PreparedImage(content=content, extension=extension)

    def store(self, prepared: PreparedImage | None) -> str | None:
        """Enregistre la photo et retourne la valeur à persister dans `image_url`."""
        if prepared is None:
            return None
        if prepared.remote_url is not None:
            return prepared.remote_url
        return self.store_bytes(prepared.content or b"", prepared.extension or "jpg")

    def store_bytes(self, content: bytes, extension: str) -> str:
        directory = _chat_images_dir()
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{extension}"
        tmp_path = directory / f".{name}.tmp"
        tmp_path.write_bytes(content)
        os.replace(tmp_path, directory / name)  # écriture atomique
        return f"{MEDIA_REF_PREFIX}{name}"

    def delete(self, stored: str | None) -> bool:
        """Supprime le fichier d'une référence `media:<nom>` (nom validé, jamais de chemin)."""
        if not stored or not stored.startswith(MEDIA_REF_PREFIX):
            return False
        name = stored[len(MEDIA_REF_PREFIX) :]
        if not _NAME_RE.match(name):
            return False
        path = _chat_images_dir() / name
        if not path.is_file():
            return False
        path.unlink()
        return True

    def public_url(self, stored: str | None, now: float | None = None) -> str | None:
        """Convertit la valeur persistée en URL exploitable par les clients."""
        if not stored or not stored.startswith(MEDIA_REF_PREFIX):
            # URL distante, ou ancien Base64 pas encore migré (voir
            # `python -m app.scripts.migrate_chat_images`).
            return stored
        name = stored[len(MEDIA_REF_PREFIX) :]
        exp = int((now or time.time()) + SIGNED_URL_TTL_SECONDS)
        return f"{CHAT_IMAGES_ROUTE}/{name}?exp={exp}&sig={_signature(name, exp)}"

    def resolve_signed(self, name: str, exp: int, sig: str) -> Path | None:
        """Retourne le fichier si la signature est valide et non expirée, sinon None."""
        if not _NAME_RE.match(name) or exp < time.time():
            return None
        if not hmac.compare_digest(_signature(name, exp), sig):
            return None
        path = _chat_images_dir() / name
        return path if path.is_file() else None


media_service = MediaService()
