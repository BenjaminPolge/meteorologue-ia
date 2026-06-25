"""Client Open-Meteo (endpoint Météo-France : modèles AROME et ARPEGE).

Doc : https://open-meteo.com/en/docs/meteofrance-api
Aucune clé requise.
"""
from __future__ import annotations

from typing import Any

import httpx

METEOFRANCE_URL = "https://api.open-meteo.com/v1/meteofrance"

# Modèles utilisés.
MODELS = ["arome_france_hd", "arpege_europe"]

# Variables horaires demandées.
HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "pressure_msl",
    "cape",
]

# Conditions courantes (analyse récente du modèle, à ne PAS confondre avec une
# observation de station).
CURRENT_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "pressure_msl",
]


async def fetch_forecast(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    forecast_days: int = 4,
    timezone: str = "Europe/Paris",
) -> dict[str, Any]:
    """Récupère AROME + ARPEGE en une requête.

    Open-Meteo suffixe chaque variable par le nom du modèle quand plusieurs
    modèles sont demandés (ex: temperature_2m_arome_france_hd).
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "models": ",".join(MODELS),
        "hourly": ",".join(HOURLY_VARS),
        "current": ",".join(CURRENT_VARS),
        "forecast_days": forecast_days,
        "timezone": timezone,
    }
    resp = await client.get(METEOFRANCE_URL, params=params)
    resp.raise_for_status()
    return resp.json()


def split_by_model(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Réorganise la réponse Open-Meteo en {model: {time, units, hourly, current}}."""
    hourly = raw.get("hourly", {}) or {}
    hourly_units = raw.get("hourly_units", {}) or {}
    current = raw.get("current", {}) or {}
    current_units = raw.get("current_units", {}) or {}
    times = hourly.get("time", [])

    out: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        suffix = f"_{model}"
        model_hourly: dict[str, list[Any]] = {}
        model_units: dict[str, str] = {}
        for var in HOURLY_VARS:
            key = f"{var}{suffix}"
            if key in hourly:
                model_hourly[var] = hourly[key]
                if key in hourly_units:
                    model_units[var] = hourly_units[key]
        model_current: dict[str, Any] = {}
        for var in CURRENT_VARS:
            key = f"{var}{suffix}"
            if key in current:
                model_current[var] = current[key]
        if model_hourly:
            out[model] = {
                "time": times,
                "units": model_units,
                "hourly": model_hourly,
                "current": model_current,
                "current_units": current_units,
            }
    return out
