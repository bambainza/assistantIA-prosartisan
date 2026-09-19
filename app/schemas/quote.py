"""Schémas Pydantic pour les devis et factures pro-forma."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QuoteItem(BaseModel):
    """Ligne de devis (fourniture, main d'œuvre, forfait)."""

    description: str = Field(
        ..., min_length=1, description="Désignation de la prestation ou fourniture"
    )
    quantite: float = Field(default=1.0, gt=0, description="Quantité ou volume")
    unite: str = Field(
        default="unité",
        description="Unité de mesure (m², m³, sac, ml, forfait, jour, heure)",
    )
    prix_unitaire: int = Field(default=0, ge=0, description="Prix unitaire en F CFA")
    total: int = Field(
        default=0, ge=0, description="Total ligne calculé (quantite x prix_unitaire)"
    )
    type_item: str = Field(
        default="FOURNITURE", description="FOURNITURE, MAIN_D_OEUVRE, FORFAIT"
    )


class QuoteCreate(BaseModel):
    """Création d'un nouveau devis ou facture pro-forma."""

    titre: str = Field(
        ..., min_length=2, max_length=200, description="Objet des travaux"
    )
    client_nom: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Nom complet ou société du client",
    )
    client_telephone: str | None = Field(
        default=None, max_length=50, description="Numéro WhatsApp/téléphone"
    )
    client_adresse: str | None = Field(
        default=None, max_length=255, description="Lieu du chantier / commune"
    )
    metier_id: int | None = Field(
        default=None, description="Identifiant du métier concerné"
    )
    items: list[QuoteItem] = Field(
        default_factory=list, description="Détail des postes et fournitures"
    )
    remise_pct: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Remise commerciale en %"
    )
    tva_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="TVA en % (0% pour micro-entreprises)",
    )
    acompte_demande_pct: float = Field(
        default=30.0, ge=0.0, le=100.0, description="Acompte exigé au démarrage (%)"
    )
    mode_paiement: str = Field(
        default="Wave / Orange Money", max_length=50, description="Mode de règlement"
    )
    delai_jours: int | None = Field(
        default=None, ge=1, description="Délai estimé d'exécution en jours ouvrés"
    )
    notes: str | None = Field(
        default=None, description="Conditions particulières ou observations"
    )


class QuoteUpdate(BaseModel):
    """Mise à jour partielle d'un devis."""

    titre: str | None = Field(default=None, min_length=2, max_length=200)
    client_nom: str | None = Field(default=None, min_length=2, max_length=150)
    client_telephone: str | None = None
    client_adresse: str | None = None
    items: list[QuoteItem] | None = None
    remise_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    tva_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    acompte_demande_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    mode_paiement: str | None = None
    delai_jours: int | None = Field(default=None, ge=1)
    notes: str | None = None


class QuoteStatusUpdate(BaseModel):
    """Mise à jour du statut commercial d'un devis."""

    statut: str = Field(
        ...,
        description="BROUILLON, ENVOYE, ACCEPTE, REFUSE, FACTURE, ANNULE",
    )


class QuoteResponse(BaseModel):
    """Représentation complète d'un devis avec totaux et partages."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    numero: str
    titre: str
    client_nom: str
    client_telephone: str | None
    client_adresse: str | None
    metier_id: int | None
    statut: str
    items: list[QuoteItem]
    total_ht: int
    remise_pct: float
    tva_pct: float
    total_ttc: int
    acompte_demande_pct: float
    montant_acompte: int
    solde_restant: int
    mode_paiement: str
    delai_jours: int | None
    notes: str | None
    date_emission: datetime
    date_validite: datetime | None
    whatsapp_share_text: str | None = None
    whatsapp_share_url: str | None = None
    created_at: datetime
    updated_at: datetime


class QuoteExtractRequest(BaseModel):
    """Requête de conversion d'une description vocale ou textuelle en devis structuré."""

    description_brute: str = Field(
        ...,
        min_length=5,
        description="Transcription vocale ou note écrite de chantier (ex: 'Changement de 3 disjoncteurs, 40m de câble 2.5 et 6 prises pour Koffi')",
    )
    client_nom: str | None = Field(default=None, description="Nom du client si connu")
    client_telephone: str | None = Field(
        default=None, description="Téléphone du client"
    )
    metier_id: int | None = Field(default=None, description="Métier de l'artisan")


class QuoteExtractResponse(BaseModel):
    """Résultat de l'extraction IA pour pré-remplissage du devis."""

    titre: str
    client_nom: str
    client_telephone: str | None
    client_adresse: str | None = None
    items: list[QuoteItem]
    delai_estime_jours: int | None
    recommandations: list[str] = Field(default_factory=list)
