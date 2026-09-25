"""Réexporte tous les modèles pour faciliter les imports.

Chaque modèle doit être importé ici : les scripts d'exploitation (purge,
réconciliation...) ne chargent pas ``app.main``, et SQLAlchemy ne résout les
relations par nom (``relationship("Role")``) que si la classe est enregistrée.
"""

from app.models.actualite import Actualite, ActualiteCategorie
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.conversation import Conversation
from app.models.document_config import DocumentConfig
from app.models.feedback import Feedback
from app.models.message import Message
from app.models.metier import Metier, SousMetier
from app.models.notification import Notification
from app.models.package import Package
from app.models.push_subscription import PushSubscription
from app.models.quota import QuotaUtilisateur
from app.models.quote import Quote
from app.models.role import Permission, Role
from app.models.subscription import UserSubscription
from app.models.transaction import TransactionMobileMoney
from app.models.user import User

__all__ = [
    "Actualite",
    "ActualiteCategorie",
    "AuditLog",
    "Base",
    "Conversation",
    "DocumentConfig",
    "Feedback",
    "Message",
    "Metier",
    "Notification",
    "Package",
    "Permission",
    "PushSubscription",
    "QuotaUtilisateur",
    "Quote",
    "Role",
    "SousMetier",
    "TransactionMobileMoney",
    "User",
    "UserSubscription",
]
