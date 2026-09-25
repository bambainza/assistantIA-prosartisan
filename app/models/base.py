"""Base déclarative SQLAlchemy partagée par tous les modèles."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class UTCNaiveDateTime(TypeDecorator[datetime]):
    """Horodatage stocké en UTC *sans* fuseau (colonnes `timestamp without time zone`).

    Le code manipule des `datetime.now(UTC)` (avec fuseau) alors que toutes les
    colonnes du schéma sont sans fuseau : asyncpg refuse ce mélange
    (« can't subtract offset-naive and offset-aware datetimes »), SQLite
    l'accepte en silence. Toute valeur avec fuseau est donc convertie en UTC
    puis rendue naïve avant l'écriture ; les lectures restent naïves (UTC).
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles ORM du projet."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: UTCNaiveDateTime}
