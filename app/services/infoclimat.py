"""Client Infoclimat (observations temps réel du réseau de stations).

Doc : https://www.infoclimat.fr/public-api/

L'API "opendata" renvoie les observations des stations à partir d'un token :
    https://www.infoclimat.fr/opendata/?method=get&format=json
        &stations[]=<ID>&start=<YYYY-MM-DD>&end=<YYYY-MM-DD>&token=<TOKEN>

Le token est lu dans la variable d'environnement INFOCLIMAT_TOKEN.

Remarque réseau : le domaine infoclimat.fr est protégé par Cloudflare. Selon
l'adresse IP d'où part la requête (certains datacenters sont filtrés), l'appel
peut renvoyer un challenge "Just a moment" (HTTP 403). Le client gère ce cas
proprement : il renvoie available=False avec la raison, et la couche
"météorologue" l'indique au lieu d'inventer une donnée.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

OPENDATA_URL = "https://www.infoclimat.fr/opendata/"

# Table intégrée des principales stations SYNOP françaises (IDs compatibles
# Infoclimat). Sert à choisir la station la plus proche sans dépendre d'un
# endpoint de listing. Surchargée par INFOCLIMAT_STATIONS si défini.
STATIONS: list[dict[str, Any]] = [
    {"id": "07015", "name": "Lille-Lesquin", "lat": 50.570, "lon": 3.097},
    {"id": "07005", "name": "Abbeville", "lat": 50.136, "lon": 1.834},
    {"id": "07037", "name": "Rouen-Boos", "lat": 49.383, "lon": 1.181},
    {"id": "07110", "name": "Brest-Guipavas", "lat": 48.444, "lon": -4.412},
    {"id": "07130", "name": "Rennes-Saint-Jacques", "lat": 48.069, "lon": -1.734},
    {"id": "07139", "name": "Alençon", "lat": 48.445, "lon": 0.110},
    {"id": "07149", "name": "Paris-Orly", "lat": 48.717, "lon": 2.384},
    {"id": "07150", "name": "Paris-Roissy-CDG", "lat": 49.013, "lon": 2.550},
    {"id": "07156", "name": "Paris-Montsouris", "lat": 48.821, "lon": 2.338},
    {"id": "07168", "name": "Troyes-Barberey", "lat": 48.325, "lon": 4.020},
    {"id": "07181", "name": "Nancy-Essey", "lat": 48.690, "lon": 6.221},
    {"id": "07190", "name": "Strasbourg-Entzheim", "lat": 48.549, "lon": 7.640},
    {"id": "07207", "name": "Pointe-de-Chemoulin", "lat": 47.234, "lon": -2.298},
    {"id": "07222", "name": "Nantes-Bouguenais", "lat": 47.150, "lon": -1.609},
    {"id": "07240", "name": "Tours-Parçay-Meslay", "lat": 47.444, "lon": 0.727},
    {"id": "07255", "name": "Bourges", "lat": 47.059, "lon": 2.360},
    {"id": "07280", "name": "Dijon-Longvic", "lat": 47.268, "lon": 5.088},
    {"id": "07299", "name": "Bâle-Mulhouse", "lat": 47.614, "lon": 7.510},
    {"id": "07335", "name": "Poitiers-Biard", "lat": 46.594, "lon": 0.314},
    {"id": "07434", "name": "Limoges-Bellegarde", "lat": 45.861, "lon": 1.175},
    {"id": "07460", "name": "Clermont-Ferrand", "lat": 45.787, "lon": 3.149},
    {"id": "07471", "name": "Le Puy-Loudes", "lat": 45.075, "lon": 3.764},
    {"id": "07481", "name": "Lyon-Saint-Exupéry", "lat": 45.726, "lon": 5.078},
    {"id": "07510", "name": "Bordeaux-Mérignac", "lat": 44.831, "lon": -0.691},
    {"id": "07535", "name": "Gourdon", "lat": 44.745, "lon": 1.397},
    {"id": "07558", "name": "Millau", "lat": 44.118, "lon": 3.020},
    {"id": "07577", "name": "Montélimar", "lat": 44.581, "lon": 4.733},
    {"id": "07591", "name": "Embrun", "lat": 44.566, "lon": 6.502},
    {"id": "07607", "name": "Mont-de-Marsan", "lat": 43.910, "lon": -0.500},
    {"id": "07621", "name": "Tarbes-Ossun", "lat": 43.188, "lon": 0.000},
    {"id": "07630", "name": "Toulouse-Blagnac", "lat": 43.621, "lon": 1.379},
    {"id": "07643", "name": "Montpellier-Fréjorgues", "lat": 43.577, "lon": 3.963},
    {"id": "07650", "name": "Marseille-Marignane", "lat": 43.438, "lon": 5.216},
    {"id": "07661", "name": "Cap Cépet", "lat": 43.079, "lon": 5.940},
    {"id": "07690", "name": "Nice", "lat": 43.649, "lon": 7.209},
    {"id": "07747", "name": "Perpignan", "lat": 42.737, "lon": 2.873},
]


@dataclass
class Station:
    id: str
    name: str
    lat: float
    lon: float
    distance_km: float


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_stations(
    latitude: float, longitude: float, limit: int = 2
) -> list[Station]:
    ranked = [
        Station(
            id=s["id"],
            name=s["name"],
            lat=s["lat"],
            lon=s["lon"],
            distance_km=_haversine_km(latitude, longitude, s["lat"], s["lon"]),
        )
        for s in STATIONS
    ]
    ranked.sort(key=lambda s: s.distance_km)
    return ranked[:limit]


def _latest_observation(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Renvoie l'observation la plus récente d'une liste (triée par date)."""
    dated = [obs for obs in series if isinstance(obs, dict) and obs.get("dh_utc")]
    if not dated:
        return None
    dated.sort(key=lambda o: o["dh_utc"])
    return dated[-1]


async def fetch_observations(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    token: str | None,
    station_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Récupère les observations récentes des stations proches.

    Renvoie toujours un dict structuré, même en cas d'échec :
        {available: bool, reason: str|None, stations: [...]}
    """
    if not token:
        return {
            "available": False,
            "reason": "Token Infoclimat absent (variable INFOCLIMAT_TOKEN non définie).",
            "stations": [],
        }

    if station_ids:
        targets = [
            Station(id=sid, name=sid, lat=latitude, lon=longitude, distance_km=0.0)
            for sid in station_ids
        ]
    else:
        targets = nearest_stations(latitude, longitude, limit=2)

    today = date.today()
    params: list[tuple[str, str]] = [
        ("method", "get"),
        ("format", "json"),
        ("start", (today - timedelta(days=1)).isoformat()),
        ("end", today.isoformat()),
        ("token", token),
    ]
    for s in targets:
        params.append(("stations[]", s.id))

    try:
        resp = await client.get(OPENDATA_URL, params=params)
    except httpx.HTTPError as exc:
        return {
            "available": False,
            "reason": f"Erreur réseau Infoclimat : {exc!s}",
            "stations": [s.__dict__ for s in targets],
        }

    if resp.status_code != 200:
        snippet = resp.text[:120].replace("\n", " ")
        reason = f"Infoclimat a renvoyé HTTP {resp.status_code}."
        if "Just a moment" in resp.text or resp.status_code == 403:
            reason += (
                " La requête a été bloquée par Cloudflare (filtrage par IP). "
                "L'appel fonctionne généralement depuis une IP non filtrée."
            )
        return {
            "available": False,
            "reason": f"{reason} ({snippet})",
            "stations": [s.__dict__ for s in targets],
        }

    try:
        data = resp.json()
    except ValueError:
        return {
            "available": False,
            "reason": "Réponse Infoclimat illisible (pas du JSON).",
            "stations": [s.__dict__ for s in targets],
        }

    # Métadonnées des stations renvoyées par Infoclimat.
    meta = {st.get("id"): st for st in (data.get("stations") or []) if isinstance(st, dict)}

    results: list[dict[str, Any]] = []
    for s in targets:
        series = data.get(s.id)
        latest = _latest_observation(series) if isinstance(series, list) else None
        station_meta = meta.get(s.id, {})
        results.append(
            {
                "id": s.id,
                "name": station_meta.get("name") or s.name,
                "distance_km": round(s.distance_km, 1),
                "latest_observation": latest,
            }
        )

    any_obs = any(r["latest_observation"] for r in results)
    return {
        "available": any_obs,
        "reason": None if any_obs else "Aucune observation récente renvoyée pour les stations proches.",
        "stations": results,
    }
