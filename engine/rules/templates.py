"""Deterministic EN/ES text (PLAN.md 14.5). No model is involved at lookup time."""

from __future__ import annotations


def mailing_mismatch(mailing_city: str, legal_city: str) -> dict[str, str]:
    return {
        "en": f"Mailed as {mailing_city}. Legally inside {legal_city}.",
        "es": f"Enviado como {mailing_city}. Legalmente dentro de {legal_city}.",
    }
