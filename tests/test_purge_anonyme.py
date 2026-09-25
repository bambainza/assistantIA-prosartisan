"""Tests du script de purge des discussions de l'ancien compte anonyme partagé."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.scripts import purge_anonymous_history as script
from app.services.chat_history_service import LEGACY_ANONYMOUS_USER_ID


class _Session:
    """Session simulée : compte les requêtes et renvoie des compteurs fixes."""

    def __init__(self, photos):
        self.requetes = []
        self.commit = AsyncMock()
        self._resultats = iter(
            [
                MagicMock(scalar_one=MagicMock(return_value=2)),  # discussions
                MagicMock(scalar_one=MagicMock(return_value=5)),  # messages
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=lambda: photos))
                ),
            ]
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self.requetes.append(stmt)
        return next(self._resultats, MagicMock())


def _brancher(monkeypatch, session, supprimees):
    monkeypatch.setattr(script, "async_session", lambda: session)
    monkeypatch.setattr(
        script.media_service, "delete", lambda ref: supprimees.append(ref) or True
    )


@pytest.mark.asyncio
async def test_dry_run_compte_sans_rien_supprimer(monkeypatch):
    session, supprimees = _Session(["media:" + "a" * 32 + ".png"]), []
    _brancher(monkeypatch, session, supprimees)

    stats = await script.purge_anonymous_history(dry_run=True)

    assert stats == {"discussions": 2, "messages": 5, "photos": 1}
    assert len(session.requetes) == 3  # uniquement des lectures
    session.commit.assert_not_awaited()
    assert supprimees == []


@pytest.mark.asyncio
async def test_purge_supprime_messages_discussions_puis_photos(monkeypatch):
    photo = "media:" + "b" * 32 + ".jpg"
    session, supprimees = _Session([photo]), []
    _brancher(monkeypatch, session, supprimees)

    stats = await script.purge_anonymous_history()

    suppressions = [str(r) for r in session.requetes[3:]]
    assert suppressions[0].startswith("DELETE FROM messages")
    assert suppressions[1].startswith("DELETE FROM conversations")
    # Seul l'ancien compte anonyme est visé.
    compiled = session.requetes[4].compile()
    assert LEGACY_ANONYMOUS_USER_ID in compiled.params.values()
    session.commit.assert_awaited_once()
    assert supprimees == [photo]
    assert stats["photos"] == 1
