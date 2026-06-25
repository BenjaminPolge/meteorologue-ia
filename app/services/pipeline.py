"""Orchestration de la couche "météorologue".

Pipeline pour chaque question :
1. Identifier localisation + échéance + type de demande (LLM).
2. Géocoder, puis récupérer EN PARALLÈLE AROME, ARPEGE (Open-Meteo) et les
   observations Infoclimat.
3. Construire un bloc de données structuré (JSON) avec le calcul de l'accord /
   divergence des modèles.
4. Faire générer la réponse de prévisionniste par le LLM.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.services import infoclimat, llm, openmeteo
from app.services.geocoding import Location, geocode

PARIS = ZoneInfo("Europe/Paris")


def _now_paris() -> datetime:
    return datetime.now(PARIS)


def _parse_local(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _clean(values: list[Any]) -> list[float]:
    return [float(v) for v in values if v is not None]


def _round_list(values: list[Any], ndigits: int = 1) -> list[Any]:
    out: list[Any] = []
    for v in values:
        out.append(round(float(v), ndigits) if v is not None else None)
    return out


def _window_indices(
    times: list[str], start: datetime | None, end: datetime | None
) -> list[int]:
    if not times:
        return []
    if start is None and end is None:
        return list(range(len(times)))
    start_naive = start.replace(tzinfo=None) if start else None
    end_naive = end.replace(tzinfo=None) if end else None
    idxs: list[int] = []
    for i, t in enumerate(times):
        dt = _parse_local(t)
        if dt is None:
            continue
        if start_naive and dt < start_naive:
            continue
        if end_naive and dt > end_naive:
            continue
        idxs.append(i)
    return idxs


def _summarize(model: dict[str, Any], idxs: list[int]) -> dict[str, Any]:
    """Agrège les variables d'un modèle sur une fenêtre d'indices."""
    hourly = model.get("hourly", {})
    units = model.get("units", {})

    def col(name: str) -> list[Any]:
        series = hourly.get(name, [])
        return [series[i] for i in idxs if i < len(series)]

    temps = _clean(col("temperature_2m"))
    precip = _clean(col("precipitation"))
    prob = _clean(col("precipitation_probability"))
    wind = _clean(col("wind_speed_10m"))
    gust = _clean(col("wind_gusts_10m"))
    cloud = _clean(col("cloud_cover"))
    pres = _clean(col("pressure_msl"))
    hum = _clean(col("relative_humidity_2m"))
    cape = _clean(col("cape"))

    return {
        "temperature_min_c": round(min(temps), 1) if temps else None,
        "temperature_max_c": round(max(temps), 1) if temps else None,
        "temperature_moy_c": round(mean(temps), 1) if temps else None,
        "precip_total_mm": round(sum(precip), 1) if precip else None,
        "precip_proba_max_pct": round(max(prob), 0) if prob else None,
        "vent_moy_kmh": round(mean(wind), 0) if wind else None,
        "rafales_max_kmh": round(max(gust), 0) if gust else None,
        "couverture_nuageuse_moy_pct": round(mean(cloud), 0) if cloud else None,
        "pression_debut_hpa": round(pres[0], 1) if pres else None,
        "pression_fin_hpa": round(pres[-1], 1) if pres else None,
        "humidite_moy_pct": round(mean(hum), 0) if hum else None,
        "cape_max_jkg": round(max(cape), 0) if cape else None,
        "unites": units,
        "n_heures": len(idxs),
    }


def _daily_summary(model: dict[str, Any]) -> list[dict[str, Any]]:
    times = model.get("time", [])
    hourly = model.get("hourly", {})
    by_day: dict[str, list[int]] = {}
    for i, t in enumerate(times):
        day = t[:10]
        by_day.setdefault(day, []).append(i)
    out: list[dict[str, Any]] = []
    for day, idxs in sorted(by_day.items()):
        temps = _clean([hourly.get("temperature_2m", [])[i] for i in idxs if i < len(hourly.get("temperature_2m", []))])
        precip = _clean([hourly.get("precipitation", [])[i] for i in idxs if i < len(hourly.get("precipitation", []))])
        gust = _clean([hourly.get("wind_gusts_10m", [])[i] for i in idxs if i < len(hourly.get("wind_gusts_10m", []))])
        cape = _clean([hourly.get("cape", [])[i] for i in idxs if i < len(hourly.get("cape", []))])
        out.append(
            {
                "date": day,
                "t_min_c": round(min(temps), 1) if temps else None,
                "t_max_c": round(max(temps), 1) if temps else None,
                "precip_total_mm": round(sum(precip), 1) if precip else None,
                "rafales_max_kmh": round(max(gust), 0) if gust else None,
                "cape_max_jkg": round(max(cape), 0) if cape else None,
            }
        )
    return out


def _focused_hourly(model: dict[str, Any], idxs: list[int], max_points: int = 18) -> dict[str, Any]:
    """Série horaire compacte sur la fenêtre (sous-échantillonnée si trop longue)."""
    times = model.get("time", [])
    hourly = model.get("hourly", {})
    if len(idxs) > max_points:
        step = max(1, len(idxs) // max_points)
        idxs = idxs[::step]
    sel_times = [times[i] for i in idxs if i < len(times)]
    out: dict[str, Any] = {"time": sel_times}
    for var in [
        "temperature_2m",
        "precipitation",
        "precipitation_probability",
        "wind_speed_10m",
        "wind_gusts_10m",
        "cloud_cover",
        "pressure_msl",
        "relative_humidity_2m",
        "cape",
    ]:
        series = hourly.get(var, [])
        out[var] = _round_list([series[i] for i in idxs if i < len(series)], 1)
    return out


def _agreement(arome: dict[str, Any], arpege: dict[str, Any]) -> dict[str, Any]:
    """Chiffre l'écart entre les deux modèles sur la fenêtre."""
    def diff(key: str) -> float | None:
        a, b = arome.get(key), arpege.get(key)
        if a is None or b is None:
            return None
        return round(abs(a - b), 1)

    temp_diff = diff("temperature_moy_c")
    precip_diff = diff("precip_total_mm")
    gust_diff = diff("rafales_max_kmh")

    verdict = "indéterminé"
    if temp_diff is not None and precip_diff is not None:
        if temp_diff <= 1.5 and precip_diff <= 1.0:
            verdict = "bon accord"
        elif temp_diff <= 3.0 and precip_diff <= 4.0:
            verdict = "accord modéré"
        else:
            verdict = "divergence notable"

    return {
        "ecart_temp_moy_c": temp_diff,
        "ecart_precip_total_mm": precip_diff,
        "ecart_rafales_max_kmh": gust_diff,
        "verdict": verdict,
        "note": (
            "AROME plus fiable à courte échéance (<48h, phénomènes locaux/convectifs) ; "
            "ARPEGE plus pertinent au-delà. Fiabilité décroissante avec l'échéance."
        ),
    }


def _model_current(model: dict[str, Any]) -> dict[str, Any]:
    cur = model.get("current", {})
    return {
        "temperature_2m": cur.get("temperature_2m"),
        "relative_humidity_2m": cur.get("relative_humidity_2m"),
        "precipitation": cur.get("precipitation"),
        "wind_speed_10m": cur.get("wind_speed_10m"),
        "wind_gusts_10m": cur.get("wind_gusts_10m"),
        "cloud_cover": cur.get("cloud_cover"),
        "pressure_msl": cur.get("pressure_msl"),
    }


def build_data_block(
    location: Location,
    intent: dict[str, Any],
    models: dict[str, dict[str, Any]],
    obs: dict[str, Any],
    now_iso: str,
) -> dict[str, Any]:
    start = _parse_local(intent.get("start_iso"))
    end = _parse_local(intent.get("end_iso"))

    arome = models.get("arome_france_hd", {})
    arpege = models.get("arpege_europe", {})
    times = arome.get("time") or arpege.get("time") or []
    idxs = _window_indices(times, start, end)
    if not idxs:
        idxs = list(range(min(len(times), 24)))

    arome_sum = _summarize(arome, idxs) if arome else {}
    arpege_sum = _summarize(arpege, idxs) if arpege else {}

    return {
        "instant_present": now_iso,
        "localisation": {
            "nom": location.label,
            "latitude": location.latitude,
            "longitude": location.longitude,
        },
        "demande": intent,
        "fenetre_analyse": {
            "debut": intent.get("start_iso"),
            "fin": intent.get("end_iso"),
            "n_heures": len(idxs),
        },
        "modeles": {
            "AROME": {
                "description": "arome_france_hd, haute résolution ~1.3km, courte échéance",
                "synthese_fenetre": arome_sum,
                "horaire_fenetre": _focused_hourly(arome, idxs) if arome else {},
                "synthese_journaliere": _daily_summary(arome) if arome else [],
                "analyse_recente_modele": _model_current(arome) if arome else {},
            },
            "ARPEGE": {
                "description": "arpege_europe, maille plus large, moyenne échéance",
                "synthese_fenetre": arpege_sum,
                "horaire_fenetre": _focused_hourly(arpege, idxs) if arpege else {},
                "synthese_journaliere": _daily_summary(arpege) if arpege else [],
                "analyse_recente_modele": _model_current(arpege) if arpege else {},
            },
        },
        "accord_modeles": _agreement(arome_sum, arpege_sum),
        "observations_infoclimat": obs,
    }


async def run_pipeline(history: list[dict[str, str]]) -> dict[str, Any]:
    """Exécute le pipeline complet et renvoie la réponse + le bloc de données."""
    now = _now_paris()
    now_iso = now.strftime("%Y-%m-%dT%H:%M")

    intent = await llm.extract_intent(history, now_iso)
    location_name = intent.get("location")

    if not location_name:
        return {
            "answer": (
                "Je peux raisonner comme un prévisionniste, mais j'ai besoin d'une "
                "localisation. Pour quelle ville ou région souhaitez-vous une analyse ?"
            ),
            "data_block": {"demande": intent, "instant_present": now_iso},
            "needs_location": True,
        }

    horizon = int(intent.get("horizon_days") or 2)
    horizon = max(1, min(horizon, 7))

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        location = await geocode(client, location_name)
        if location is None:
            return {
                "answer": (
                    f"Je n'ai pas trouvé la localisation « {location_name} ». "
                    "Pouvez-vous préciser la ville (et le pays si besoin) ?"
                ),
                "data_block": {"demande": intent, "instant_present": now_iso},
                "needs_location": True,
            }

        forecast_task = openmeteo.fetch_forecast(
            client, location.latitude, location.longitude, forecast_days=horizon
        )
        obs_task = infoclimat.fetch_observations(
            client,
            location.latitude,
            location.longitude,
            token=settings.infoclimat_token,
            station_ids=settings.infoclimat_stations or None,
        )
        raw_forecast, obs = await asyncio.gather(forecast_task, obs_task)

    models = openmeteo.split_by_model(raw_forecast)
    data_block = build_data_block(location, intent, models, obs, now_iso)

    answer = await llm.generate_answer(history, data_block)
    return {"answer": answer, "data_block": data_block, "needs_location": False}
