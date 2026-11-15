"""Pseudonymisation des cas : HMAC-SHA256 à clé par clinique (la clé reste hors chaîne)."""
from __future__ import annotations

import base64
import hashlib
import hmac


def case_pseudonym(clinic_key: bytes, patient_id: str, length: int = 16) -> str:
    mac = hmac.new(clinic_key, patient_id.encode("utf-8"), hashlib.sha256).digest()
    return "P-" + base64.b32encode(mac).decode("ascii").rstrip("=")[:length]
