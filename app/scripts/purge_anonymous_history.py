"""
Purge des discussions de l'ancien compte anonyme partagé.

Jusqu'ici, toutes les sessions non connectées enregistraient leurs
discussions sous un même compte « anonyme », lisibles par n'importe quel
autre visiteur non connecté (fuite de confidentialité). Le serveur n'y écrit
plus rien ; ce script supprime l'existant : discussions, messages et photos
de chantier associées (`UPLOAD_DIR/chat_images/`). Les feedbacks sont
conservés, détachés de la discussion (`ON DELETE SET NULL`).

Irréversible : lancer d'abord avec `--dry-run`. À exécuter dans le conteneur
qui monte `UPLOAD_DIR`.

Usage : python -m app.scripts.purge_anonymous_history [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import delete, func, select

from app.db.session import async_session
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.chat_history_service import LEGACY_ANONYMOUS_USER_ID
from app.services.media_service import MEDIA_REF_PREFIX, media_service

logger = logging.getLogger(__name__)


async def purge_anonymous_history(dry_run: bool = False) -> dict[str, int]:
    """Supprime discussions, messages et photos du compte anonyme hérité."""
    async with async_session() as session:
        conv_ids = select(Conversation.id).where(
            Conversation.user_id == LEGACY_ANONYMOUS_USER_ID
        )
        nb_discussions = (
            await session.execute(select(func.count()).select_from(conv_ids.subquery()))
        ).scalar_one()
        nb_messages = (
            await session.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id.in_(conv_ids)
                )
            )
        ).scalar_one()
        photos = (
            (
                await session.execute(
                    select(Message.image_url).where(
                        Message.conversation_id.in_(conv_ids),
                        Message.image_url.like(f"{MEDIA_REF_PREFIX}%"),
                    )
                )
            )
            .scalars()
            .all()
        )
        stats = {
            "discussions": nb_discussions,
            "messages": nb_messages,
            "photos": len(photos),
        }
        if dry_run:
            return stats

        # Messages supprimés explicitement : ne dépend pas de l'activation des
        # cascades de clés étrangères (SQLite en développement).
        await session.execute(
            delete(Message).where(Message.conversation_id.in_(conv_ids))
        )
        await session.execute(
            delete(Conversation).where(Conversation.user_id == LEGACY_ANONYMOUS_USER_ID)
        )
        await session.commit()

    # Fichiers supprimés après le commit : en cas d'échec de la base, aucune
    # référence ne pointe vers une photo déjà effacée.
    stats["photos"] = sum(1 for ref in photos if media_service.delete(ref))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stats = asyncio.run(purge_anonymous_history(args.dry_run))
    prefixe = "À supprimer" if args.dry_run else "Supprimés"
    print(
        f"{prefixe} — discussions : {stats['discussions']}, messages : "
        f"{stats['messages']}, photos : {stats['photos']}"
    )


if __name__ == "__main__":
    main()
