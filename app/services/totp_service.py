"""Service : Authentification à deux facteurs (TOTP) pour les comptes admin."""

from __future__ import annotations

import pyotp

_ISSUER = "ProsArtisan IA Expert"


class TotpService:
    """Génération et vérification de codes TOTP (RFC 6238)."""

    def generate_secret(self) -> str:
        """Génère un nouveau secret TOTP (encodé base32)."""
        return pyotp.random_base32()

    def get_provisioning_uri(self, secret: str, account_email: str) -> str:
        """URI `otpauth://` à encoder en QR code par une app type Google Authenticator."""
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=account_email, issuer_name=_ISSUER
        )

    def verify_code(self, secret: str, code: str) -> bool:
        """Vérifie un code à 6 chiffres avec une fenêtre de tolérance d'une période (±30s)."""
        if not secret or not code:
            return False
        try:
            return pyotp.totp.TOTP(secret).verify(code, valid_window=1)
        except Exception:
            return False


totp_service = TotpService()
