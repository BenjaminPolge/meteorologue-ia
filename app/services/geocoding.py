"""Géocodage ville -> latitude/longitude via l'API gratuite d'Open-Meteo."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass
class Location:
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None
    timezone: str | None = None

    @property
    def label(self) -> str:
        parts = [self.name]
        if self.admin1:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


# Boîte englobante approximative de l'Europe (domaine pertinent pour
# AROME/ARPEGE). Sert à écarter les homonymes lointains (ex: l'île
# "Île-de-France" au Groenland).
_EUROPE_BBOX = (34.0, 72.0, -25.0, 45.0)  # lat_min, lat_max, lon_min, lon_max


def _in_europe(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = _EUROPE_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _pick_result(results: list[dict]) -> dict:
    """Privilégie la France, puis l'Europe, sinon la première correspondance.

    L'application cible la météo française (modèles Météo-France), donc en cas
    d'homonymie on préfère un résultat en France ou en Europe.
    """
    for r in results:
        if r.get("country_code") == "FR":
            return r
    for r in results:
        try:
            if _in_europe(float(r["latitude"]), float(r["longitude"])):
                return r
        except (KeyError, TypeError, ValueError):
            continue
    return results[0]


async def geocode(client: httpx.AsyncClient, name: str) -> Location | None:
    """Renvoie la meilleure correspondance pour un nom de lieu, ou None."""
    params = {
        "name": name,
        "count": 10,
        "language": "fr",
        "format": "json",
    }
    resp = await client.get(GEOCODING_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    r = _pick_result(results)
    return Location(
        name=r.get("name", name),
        latitude=float(r["latitude"]),
        longitude=float(r["longitude"]),
        country=r.get("country"),
        admin1=r.get("admin1"),
        timezone=r.get("timezone"),
    )
