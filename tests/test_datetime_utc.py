"""Horodatages : toujours écrits en UTC sans fuseau (colonnes `timestamp without time zone`).

SQLite accepte un `datetime` avec fuseau là où PostgreSQL/asyncpg le refuse :
sans conversion, l'activation d'un Pass payé échouait en production.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.base import UTCNaiveDateTime
from app.models.conversation import Conversation
from app.models.quota import QuotaUtilisateur
from app.models.transaction import TransactionMobileMoney
from app.services.payment_service import payment_service


def test_valeur_avec_fuseau_convertie_en_utc_naif():
    fuseau_plus_2 = timezone(timedelta(hours=2))
    valeur = datetime(2026, 9, 25, 14, 0, tzinfo=fuseau_plus_2)

    stockee = UTCNaiveDateTime().process_bind_param(valeur, dialect=None)

    assert stockee == datetime(2026, 9, 25, 12, 0, tzinfo=UTC).replace(tzinfo=None)
    assert stockee.tzinfo is None


def test_valeur_naive_et_none_inchangees():
    naive = datetime(2026, 9, 25, 12, 0, tzinfo=UTC).replace(tzinfo=None)
    assert UTCNaiveDateTime().process_bind_param(naive, dialect=None) is naive
    assert UTCNaiveDateTime().process_bind_param(None, dialect=None) is None


def test_colonnes_datetime_utilisent_le_type_utc():
    for colonne in (
        QuotaUtilisateur.__table__.c.date_fin_premium,
        Conversation.__table__.c.updated_at,
        TransactionMobileMoney.__table__.c.refunded_at,
    ):
        assert isinstance(colonne.type, UTCNaiveDateTime), colonne


@pytest.mark.asyncio
async def test_pass_active_avec_une_date_de_fin_valide():
    quota = QuotaUtilisateur(user_id=uuid.uuid4(), credits_requetes=0)
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=quota))
    )
    txn = TransactionMobileMoney(user_id=quota.user_id, type_achat="pass_24h")

    await payment_service._crediter(db, txn)

    # Le type d'abonnement du compte suit le Pass payé (statistiques admin).
    maj = db.execute.await_args_list[-1].args[0]
    assert str(maj).startswith("UPDATE users")
    assert maj.compile().params["type_abonnement"] == "pass_24h"

    fin = UTCNaiveDateTime().process_bind_param(quota.date_fin_premium, None)
    attendu = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24)
    assert abs(fin - attendu) < timedelta(minutes=1)
