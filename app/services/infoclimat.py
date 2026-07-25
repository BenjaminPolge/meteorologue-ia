"""Client Infoclimat (observations temps réel du réseau de stations).

Doc : https://www.infoclimat.fr/public-api/

L'API "opendata" (v2) renvoie les observations des stations à partir d'un token :
    https://www.infoclimat.fr/opendata/?version=2&method=get&format=json
        &stations[]=<ID>&start=<YYYY-MM-DD>&end=<YYYY-MM-DD>&token=<TOKEN>

Le token est lié à l'adresse IP déclarée lors de sa création côté Infoclimat ;
les requêtes doivent donc partir de cette IP.

Le token est lu dans la variable d'environnement INFOCLIMAT_TOKEN.

Remarque réseau : le domaine infoclimat.fr est protégé par Cloudflare. Selon
l'adresse IP d'où part la requête (certains datacenters sont filtrés), l'appel
peut renvoyer un challenge "Just a moment" (HTTP 403). Le client gère ce cas
proprement : il renvoie available=False avec la raison, et la couche
"météorologue" l'indique au lieu d'inventer une donnée.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

OPENDATA_URL = "https://www.infoclimat.fr/opendata/"

STATIONS: list[dict[str, Any]] = []


def _load_stations() -> None:
    global STATIONS
    if STATIONS:
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    geojson_path = os.path.join(base_dir, "stations.geojson")

    if os.path.exists(geojson_path):
        try:
            with open(geojson_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for feature in data.get("features", []):
                    props = feature.get("properties", {})
                    geom = feature.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    # Only include infoclimat.fr (StatIC) stations since SYNOP are restricted for free keys
                    if props.get("license", {}).get("source") == "infoclimat.fr" and len(coords) == 2:
                        STATIONS.append({
                            "id": props.get("id"),
                            "name": props.get("name"),
                            "lat": coords[1],
                            "lon": coords[0]
                        })
        except Exception as e:
            pass

    if not STATIONS:
        # Fallback list of known working StatIC stations
        STATIONS = [
            {"id": "000B3", "name": "Mulhouse", "lat": 47.746, "lon": 7.343},
            {"id": "00004", "name": "Nice-Carabacel", "lat": 43.705, "lon": 7.272},
            {"id": "00002", "name": "Le Vigan", "lat": 43.990, "lon": 3.602},
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
    _load_stations()
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
        ("version", "2"),
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
        series = data.get("hourly", {}).get(s.id)
        latest = _latest_observation(series) if isinstance(series, list) else None
        
        if latest and "dh_utc" in latest:
            try:
                from datetime import datetime
                from zoneinfo import ZoneInfo
                dt_utc = datetime.strptime(latest["dh_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
                dt_local = dt_utc.astimezone(ZoneInfo("Europe/Paris"))
                latest["heure_locale"] = dt_local.strftime("%Y-%m-%d %H:%M (heure locale Paris)")
            except Exception:
                pass

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
