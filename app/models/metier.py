"""Modèles ORM : Métiers et Sous-métiers."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Metier(Base):
    """Un secteur d'activité artisanale (ex: Bâtiment, Artisanat d'art)."""

    __tablename__ = "metiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # Relations
    sous_metiers: Mapped[list["SousMetier"]] = relationship(
        back_populates="metier", cascade="all, delete-orphan"
    )


class SousMetier(Base):
    """Une spécialité au sein d'un métier (ex: Maçonnerie → Gros œuvre)."""

    __tablename__ = "sous_metiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    metier_id: Mapped[int] = mapped_column(
        ForeignKey("metiers.id", ondelete="CASCADE"), nullable=False
    )
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Relations
    metier: Mapped["Metier"] = relationship(back_populates="sous_metiers")
