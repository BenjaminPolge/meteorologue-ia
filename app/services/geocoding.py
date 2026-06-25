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


async def geocode(client: httpx.AsyncClient, name: str) -> Location | None:
    """Renvoie la première correspondance pour un nom de lieu, ou None."""
    params = {
        "name": name,
        "count": 1,
        "language": "fr",
        "format": "json",
    }
    resp = await client.get(GEOCODING_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    return Location(
        name=r.get("name", name),
        latitude=float(r["latitude"]),
        longitude=float(r["longitude"]),
        country=r.get("country"),
        admin1=r.get("admin1"),
        timezone=r.get("timezone"),
    )
