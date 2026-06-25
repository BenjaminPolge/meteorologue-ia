"""Configuration de l'application, lue depuis l'environnement.

Aucune clé n'est codée en dur : tout est lu via les variables d'environnement.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv est optionnel
    pass


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    # --- OpenAI ---
    openai_api_key: str | None = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    # Le modèle est configurable. Valeur demandée par défaut : gpt-5.5.
    # Surchargez avec OPENAI_MODEL si ce nom n'est pas disponible sur votre compte.
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5.5")
    )
    openai_base_url: str | None = field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL")
    )

    # --- Infoclimat (observations temps réel) ---
    infoclimat_token: str | None = field(
        default_factory=lambda: os.getenv("INFOCLIMAT_TOKEN")
    )
    # Liste de stations à privilégier (IDs Infoclimat / SYNOP), optionnel.
    infoclimat_stations: list[str] = field(
        default_factory=lambda: _split_csv(os.getenv("INFOCLIMAT_STATIONS"))
    )

    # --- Réglages réseau ---
    http_timeout: float = field(
        default_factory=lambda: float(os.getenv("HTTP_TIMEOUT", "20"))
    )

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
