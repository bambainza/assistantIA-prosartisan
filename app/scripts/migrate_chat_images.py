"""
Reprise des photos de chantier stockées en Base64 dans `messages.image_url`.

Chaque photo est écrite dans `UPLOAD_DIR/chat_images/` puis remplacée en base
par sa référence `media:<nom>`. Une valeur illisible (non image, corrompue) est
remplacée par NULL : elle ne pouvait de toute façon pas s'afficher.

Idempotent (seules les valeurs `data:` restantes sont traitées) et exécuté
par lots courts pour ne pas verrouiller la table. Script séparé des migrations
Alembic car il écrit sur le disque : il doit tourner là où `UPLOAD_DIR` est
monté (conteneur `app`).

Usage : python -m app.scripts.migrate_chat_images [--batch-size 50] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.db.session import async_session
from app.models.message import Message
from app.services.media_service import ImageInvalideError, media_service

logger = logging.getLogger(__name__)


async def migrate_chat_images(
    batch_size: int = 50, dry_run: bool = False
) -> dict[str, int]:
    """Déplace les photos Base64 vers le stockage fichiers ; retourne les compteurs."""
    stats = {"migrees": 0, "invalides": 0}
    dernier_id = None
    while True:
        async with async_session() as session:
            stmt = (
                select(Message)
                .where(Message.image_url.like("data:%"))
                .order_by(Message.id)
                .limit(batch_size)
            )
            if dernier_id is not None:
                stmt = stmt.where(Message.id > dernier_id)
            messages = (await session.execute(stmt)).scalars().all()
            if not messages:
                return stats

            for message in messages:
                dernier_id = message.id
                try:
                    prepared = media_service.prepare_chat_image(message.image_url)
                except ImageInvalideError as exc:
                    logger.warning("Photo illisible (message %s) : %s", message.id, exc)
                    stats["invalides"] += 1
                    if not dry_run:
                        message.image_url = None
                    continue
                stats["migrees"] += 1
                if not dry_run:
                    message.image_url = media_service.store(prepared)

            if not dry_run:
                await session.commit()
            logger.info("Lot traité : %s", stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stats = asyncio.run(migrate_chat_images(args.batch_size, args.dry_run))
    print(
        f"Photos migrées : {stats['migrees']} — valeurs illisibles : {stats['invalides']}"
    )


if __name__ == "__main__":
    main()
