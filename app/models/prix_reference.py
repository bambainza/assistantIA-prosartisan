"""Modèle ORM : grille de prix de référence administrable (devis artisans).

Les prix des devis pré-remplis par l'IA viennent exclusivement de cette
grille, tenue par l'administration : le LLM n'extrait que les désignations et
les quantités, jamais les prix (garde-fou « zéro hallucination » appliqué aux
montants).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PrixReference(Base):
    """Prix unitaire de référence d'une fourniture ou d'une prestation."""

    __tablename__ = "prix_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    designation: Mapped[str] = mapped_column(String(200), nullable=False)
    # Unité de facturation (sac, m3, ml, m2, unite, jour, forfait...) : un prix
    # n'est appliqué qu'à une ligne exprimée dans la même unité.
    unite: Mapped[str] = mapped_column(String(30), nullable=False)
    # Montant en F CFA, entier (jamais de décimales).
    prix_unitaire: Mapped[int] = mapped_column(Integer, nullable=False)
    type_item: Mapped[str] = mapped_column(
        String(20), nullable=False, default="FOURNITURE"
    )
    # Synonymes séparés par des virgules (ex. "parpaing 15, agglo creux 15").
    mots_cles: Mapped[str | None] = mapped_column(String(500), default=None)
    metier_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("metiers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Commune ou ville du relevé ; vide = valable partout.
    commune: Mapped[str | None] = mapped_column(String(100), default=None)
    # Origine du prix (quincaillerie, mercuriale, relevé terrain...).
    source: Mapped[str | None] = mapped_column(String(255), default=None)
    date_releve: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
