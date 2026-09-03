"""Run-relevant conditions: weather, pollen, air-quality forecast, terrain.

Deliberately not a weather application. `docs/basel-wetter.html` is one and it
is much better at it; what a run planner needs is the handful of numbers that
change whether you go out and how it will feel, attached to the hour you chose.

Everything here is **forecast** or **derived**, never measured and never
modelled-annual. It gets its own provenance class for that reason:

    forecast   A model's expectation for a future hour. Will be wrong sometimes,
               and carries the model and run time that produced it.
    derived    Computed from a public elevation model. Approximate by
               construction — see the note on grade below.

Sources:
    Open-Meteo forecast API        temperature, precipitation, wind
    Open-Meteo air-quality API     European AQI, PM2.5/PM10/NO2, pollen
    Open-Meteo elevation API       Copernicus GLO-90 digital elevation model

On grade specifically: GLO-90 is a 90 m model. Two adjacent samples on a city
street differ mostly by model noise, and dividing that noise by a short
horizontal distance manufactures alarming gradients that are not there. So the
profile is resampled to a fixed spacing, smoothed over a window wider than the
model's own resolution, and the result is labelled approximate. A believable
4% is more useful than a fictional 15%.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

FORECAST_API = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
ELEVATION_API = "https://api.open-meteo.com/v1/elevation"
ATTRIBUTION = "Weather, air-quality forecast and elevation: Open-Meteo (CC BY 4.0)"

FORECAST = "forecast"
DERIVED = "derived"

WEATHER_FIELDS = (
    "temperature_2m", "apparent_temperature", "precipitation_probability",
    "precipitation", "wind_speed_10m", "wind_direction_10m", "relative_humidity_2m",
)
AIR_FIELDS = (
    "european_aqi", "pm2_5", "pm10", "nitrogen_dioxide", "ozone",
    "alder_pollen", "birch_pollen", "grass_pollen", "mugwort_pollen",
    "olive_pollen", "ragweed_pollen",
)
POLLEN_FIELDS = tuple(f for f in AIR_FIELDS if f.endswith("_pollen"))

# Open-Meteo publishes pollen as grains/m3. These are the CAMS severity bands.
POLLEN_BANDS = ((0, "none"), (1, "low"), (20, "moderate"), (100, "high"), (300, "very high"))

# Sampling and smoothing for the elevation profile.
SAMPLE_SPACING_M = 50.0
SMOOTHING_WINDOW_M = 250.0        # comfortably wider than the 90 m DEM
GRADE_WINDOW_M = 200.0


def _bearing_name(degrees: Optional[float]) -> Optional[str]:
    if degrees is None:
        return None
    names = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return names[int((degrees % 360) / 45.0 + 0.5) % 8]


def pollen_band(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    label = "none"
    for threshold, name in POLLEN_BANDS:
        if value >= threshold:
            label = name
    return label


def _pick_hour(payload: dict, fields: Sequence[str], hour_iso: Optional[str]) -> dict:
    """Take one hour out of an Open-Meteo hourly block.

    Without a requested hour this is the current one, not the first in the
    block — which is midnight, and would quietly report last night's weather.
    """
    from datetime import datetime

    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return {}
    wanted = hour_iso or datetime.now().strftime("%Y-%m-%dT%H")
    index = 0
    for i, stamp in enumerate(times):
        if stamp.startswith(wanted):
            index = i
            break
    out = {"time": times[index]}
    for field in fields:
        values = hourly.get(field)
        if values and index < len(values):
            out[field] = values[index]
    return out


def fetch_conditions(lat: float, lon: float, *, hour_iso: Optional[str] = None,
                     timeout: float = 15.0) -> dict:
    """Weather, air-quality forecast and pollen for one point and one hour.

    Network-facing. Returns a `partial` record rather than raising when one of
    the two services is unavailable: a missing wind speed should not stop
    someone exporting a route.
    """
    import httpx

    result: Dict[str, object] = {
        "classification": FORECAST,
        "explanation": (
            "A model's expectation for this hour, not a measurement. "
            "It will sometimes be wrong."
        ),
        "source": "Open-Meteo",
        "attribution": ATTRIBUTION,
        "license": "CC BY 4.0",
    }
    errors = []
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        try:
            weather = client.get(FORECAST_API, params={
                "latitude": lat, "longitude": lon, "timezone": "Europe/Zurich",
                "hourly": ",".join(WEATHER_FIELDS), "forecast_days": 2,
            }).json()
            picked = _pick_hour(weather, WEATHER_FIELDS, hour_iso)
            result["weather"] = {
                "time": picked.get("time"),
                "temperature_c": picked.get("temperature_2m"),
                "apparent_temperature_c": picked.get("apparent_temperature"),
                "precipitation_probability_pct": picked.get("precipitation_probability"),
                "precipitation_mm": picked.get("precipitation"),
                "wind_speed_kmh": picked.get("wind_speed_10m"),
                "wind_direction_deg": picked.get("wind_direction_10m"),
                "wind_direction": _bearing_name(picked.get("wind_direction_10m")),
                "humidity_pct": picked.get("relative_humidity_2m"),
                "model_run": weather.get("generationtime_ms") is not None,
            }
        except Exception as exc:
            errors.append(f"weather: {exc}")
        try:
            air = client.get(AIR_QUALITY_API, params={
                "latitude": lat, "longitude": lon, "timezone": "Europe/Zurich",
                "hourly": ",".join(AIR_FIELDS), "forecast_days": 2,
            }).json()
            picked = _pick_hour(air, AIR_FIELDS, hour_iso)
            result["air_quality"] = {
                "time": picked.get("time"),
                "european_aqi": picked.get("european_aqi"),
                "pm2_5": picked.get("pm2_5"),
                "pm10": picked.get("pm10"),
                "nitrogen_dioxide": picked.get("nitrogen_dioxide"),
                "ozone": picked.get("ozone"),
                "note": (
                    "Regional forecast for the city, not a street-level value. "
                    "It cannot separate one route from another."
                ),
            }
            pollen = {}
            for field in POLLEN_FIELDS:
                value = picked.get(field)
                if value is not None:
                    pollen[field.replace("_pollen", "")] = {
                        "grains_per_m3": value, "band": pollen_band(value),
                    }
            result["pollen"] = {
                "values": pollen,
                "worst": max(
                    (k for k in pollen),
                    key=lambda k: pollen[k]["grains_per_m3"], default=None,
                ) if pollen else None,
                "unit": "grains/m3",
            }
        except Exception as exc:
            errors.append(f"air quality: {exc}")
    if errors:
        result["partial"] = errors
    return result


# --- terrain ---------------------------------------------------------------


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def resample(coordinates: Sequence[Sequence[float]],
             spacing_m: float = SAMPLE_SPACING_M) -> List[Tuple[float, float, float]]:
    """Points every `spacing_m` along the route, with cumulative distance."""
    if len(coordinates) < 2:
        return [(c[0], c[1], 0.0) for c in coordinates]
    out: List[Tuple[float, float, float]] = [(coordinates[0][0], coordinates[0][1], 0.0)]
    carried = 0.0
    travelled = 0.0
    for a, b in zip(coordinates, coordinates[1:]):
        leg = _haversine_m((a[0], a[1]), (b[0], b[1]))
        if leg <= 0:
            continue
        position = spacing_m - carried
        while position < leg:
            t = position / leg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                        travelled + position))
            position += spacing_m
        carried = (carried + leg) % spacing_m
        travelled += leg
    out.append((coordinates[-1][0], coordinates[-1][1], travelled))
    return out


def smooth(values: Sequence[float], distances: Sequence[float],
           window_m: float = SMOOTHING_WINDOW_M) -> List[float]:
    """Moving average over a window wider than the elevation model's resolution.

    Without this, 90 m DEM noise between two 50 m samples becomes a double-digit
    gradient that no runner will ever find on the ground.
    """
    out = []
    for i, centre in enumerate(distances):
        lo = hi = i
        while lo > 0 and centre - distances[lo - 1] <= window_m / 2:
            lo -= 1
        while hi < len(distances) - 1 and distances[hi + 1] - centre <= window_m / 2:
            hi += 1
        window = values[lo:hi + 1]
        out.append(sum(window) / len(window))
    return out


def terrain_profile(elevations: Sequence[float], distances: Sequence[float]) -> dict:
    """Ascent, descent and a believable maximum grade."""
    if len(elevations) < 2:
        return {"classification": DERIVED, "ascent_m": None, "descent_m": None}
    smoothed = smooth(elevations, distances)
    ascent = sum(max(0.0, b - a) for a, b in zip(smoothed, smoothed[1:]))
    descent = sum(max(0.0, a - b) for a, b in zip(smoothed, smoothed[1:]))

    # Grade over a window, not between adjacent samples.
    grades = []
    j = 0
    for i, start in enumerate(distances):
        while j < len(distances) - 1 and distances[j] - start < GRADE_WINDOW_M:
            j += 1
        run = distances[j] - start
        if run >= GRADE_WINDOW_M * 0.8:
            grades.append(abs(smoothed[j] - smoothed[i]) / run * 100.0)
    return {
        "classification": DERIVED,
        "explanation": (
            "Sampled from a 90 m public elevation model and smoothed over "
            f"{SMOOTHING_WINDOW_M:.0f} m. Approximate: good enough to compare "
            "routes, not a survey."
        ),
        "source": "Open-Meteo elevation API (Copernicus GLO-90)",
        "attribution": ATTRIBUTION,
        "ascent_m": round(ascent),
        "descent_m": round(descent),
        "min_elevation_m": round(min(smoothed), 1),
        "max_elevation_m": round(max(smoothed), 1),
        "max_grade_pct": round(max(grades), 1) if grades else None,
        "grade_window_m": GRADE_WINDOW_M,
        "profile": [
            {"km": round(d / 1000.0, 2), "elevation_m": round(e, 1)}
            for d, e in zip(distances, smoothed)
        ],
    }


def fetch_terrain(coordinates: Sequence[Sequence[float]], *, timeout: float = 15.0,
                  max_points: int = 100) -> dict:
    """Elevation along a route, resampled, smoothed and summarised."""
    import httpx

    points = resample(coordinates)
    if len(points) > max_points:                 # the API takes 100 per call
        step = math.ceil(len(points) / max_points)
        points = points[::step]
    if len(points) < 2:
        return {"classification": DERIVED, "ascent_m": None, "descent_m": None}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            payload = client.get(ELEVATION_API, params={
                "latitude": ",".join(f"{p[1]:.5f}" for p in points),
                "longitude": ",".join(f"{p[0]:.5f}" for p in points),
            }).json()
        elevations = payload.get("elevation") or []
    except Exception as exc:
        return {"classification": DERIVED, "unavailable": str(exc),
                "ascent_m": None, "descent_m": None}
    if len(elevations) != len(points):
        return {"classification": DERIVED, "unavailable": "unexpected response length",
                "ascent_m": None, "descent_m": None}
    return terrain_profile(elevations, [p[2] for p in points])
