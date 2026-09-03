"""HTTP surface for the run planner.

Mounted as its own router so the existing API is untouched. Two endpoints:

    GET /run/loops    candidate loops for a pin, distance, pace and hour
    GET /run/gpx      the chosen loop as a GPX file with provenance extensions

Every loop response carries its coverage and its parameters, because a value
computed for one pace at one hour over 15% of the network is not a fact about
Basel and must not arrive looking like one.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, NamedTuple, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .attribute import attribute_readings, _segment_midpoints
from .baseline import AirBaseline
from .exposure import DEFAULT_PACE_MIN_PER_KM
from .gpx import route_to_gpx
from .loops import generate_loops
from .sources.base import AirSource
from .sources.basel_tram import DEFAULT_CACHE as TRAM_CACHE
from .sources.fixture_source import FixtureAirSource

router = APIRouter(prefix="/run", tags=["run"])

MIN_DISTANCE_M, MAX_DISTANCE_M = 1000, 25000
MIN_PACE, MAX_PACE = 3.0, 12.0


class Prepared(NamedTuple):
    """Everything the two endpoints need, built once."""

    network: object
    segments: dict
    coverage: object
    source: AirSource
    network_note: str
    source_note: Optional[str]
    source_provenance: dict
    baseline: dict                      # segment id -> modelled NO2
    baseline_provenance: Optional[dict]


def _fixture_mode() -> bool:
    """The suite and the offline demo both pin every source to `fixture`."""
    return os.getenv("BASEL_STREET_NETWORK_SOURCE", "auto").lower() == "fixture"


def _load_network():
    """The prepared Basel walking network, or the deterministic grid.

    `load_network` never downloads and degrades to a fixture with a stated
    reason, so a missing cache cannot take the planner down.
    """
    if _fixture_mode():
        from .testing import fixture_network

        return fixture_network(), "deterministic grid (fixture mode)"
    from ..street_sources import load_network

    network = load_network("walk")
    provenance = getattr(network, "provenance", {}) or {}
    if provenance.get("mode") == "fixture":
        return network, f"fixture grid: {provenance.get('fallback_reason', 'no prepared cache')}"
    edges = network.graph.number_of_edges()
    return network, f"prepared OSM walking network, {edges} segments"


def _load_baseline(network):
    """Modelled NO2 per segment, from the clipped federal raster.

    Optional by design: the planner still works without it, and says so, but
    the ranking falls back to values that cannot separate the routes.
    """
    if not AirBaseline.available():
        return {}, None
    try:
        baseline = AirBaseline()
        ids, xs, ys, _ = _segment_midpoints(network)
        values = baseline.sample(xs, ys, "no2")
        return (
            {sid: value for sid, value in zip(ids, values) if value is not None},
            baseline.provenance("no2"),
        )
    except Exception:                   # a missing baseline must not break the planner
        return {}, None


def _load_air_source():
    """Real tram readings when the export is cached; the synthetic field otherwise.

    The fallback is deliberately loud. A demo quietly serving a synthetic field
    as if it were measurements would undo the entire point of the layer.
    """
    if _fixture_mode():
        return FixtureAirSource(), "Synthetic air field — not measurements."
    if not TRAM_CACHE.exists():
        return FixtureAirSource(), (
            "Synthetic air field — not measurements. No cached export at "
            f"{TRAM_CACHE}; run `python -m app.air.prepare` to fetch dataset 100113."
        )
    from .sources.basel_tram import BaselTramAirSource

    return BaselTramAirSource(TRAM_CACHE), None


@lru_cache(maxsize=1)
def _prepared() -> Prepared:
    """Network plus attributed air, built once.

    Falls back to the fixture air field when no prepared readings exist, and
    the response says which one it used — a demo silently serving synthetic
    data as if it were measurements would undo the entire point.
    """
    network, network_note = _load_network()
    source, source_note = _load_air_source()
    try:
        readings = source.readings()
    except Exception as exc:       # a corrupt export must not take the planner down
        source, source_note = FixtureAirSource(), (
            "Synthetic air field — not measurements. Could not read the cached "
            f"export: {exc}"
        )
        readings = source.readings()
    segments, coverage = attribute_readings(
        network, readings, error_band=source.error_band("pm25"),
    )
    baseline, baseline_provenance = _load_baseline(network)
    return Prepared(
        network, segments, coverage, source, network_note, source_note,
        _source_provenance(source, readings), baseline, baseline_provenance,
    )


def _source_provenance(source: AirSource, readings) -> dict:
    """Dataset, licence and window, read once off the readings we already have."""
    statistics = getattr(source, "statistics", None) or {}
    window = sorted((statistics.get("readings_per_month") or {}).keys())
    record = dict(readings[0].provenance or {}) if readings else {}
    return {
        "dataset": record.get("dataset"),
        "dataset_title": record.get("dataset_title"),
        "source_url": record.get("source_url"),
        "license": record.get("license"),
        "retrieved_at": record.get("retrieved_at"),
        "sensor_class": record.get("sensor_class"),
        "readings_total": statistics.get("readings_total") or len(readings),
        "measurement_window": (
            {"first_month": window[0], "last_month": window[-1]} if window else None
        ),
    }


@router.get("/loops")
def loops(
    lon: float = Query(..., description="start longitude"),
    lat: float = Query(..., description="start latitude"),
    distance_m: float = Query(5000, ge=MIN_DISTANCE_M, le=MAX_DISTANCE_M),
    pace_min_per_km: float = Query(DEFAULT_PACE_MIN_PER_KM, ge=MIN_PACE, le=MAX_PACE),
    hour: Optional[int] = Query(None, ge=0, le=23),
    limit: int = Query(3, ge=1, le=6),
):
    prepared = _prepared()
    network, segments = prepared.network, prepared.segments
    candidates = generate_loops(
        network, segments, lon=lon, lat=lat, target_m=distance_m,
        pace_min_per_km=pace_min_per_km, hour=hour, limit=limit,
        baseline=prepared.baseline,
    )
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=(
                "No loop near that distance from this point. Try a different "
                "distance or a start closer to the network."
            ),
        )
    source = prepared.source
    return {
        "loops": [c.as_dict(network) for c in candidates],
        "network_coverage": prepared.coverage.as_dict(),
        "air_source": {
            "mode": source.mode,
            "fixture": source.mode == "fixture",
            "warning": prepared.source_note,
            "network": prepared.network_note,
            **prepared.source_provenance,
        },
        "baseline_source": prepared.baseline_provenance,
        "ranked_by": (
            "modelled annual-mean NO2 (federal raster)"
            if prepared.baseline else
            "measured PM2.5 per measured minute"
        ),
    }


@router.get("/gpx")
def gpx(
    lon: float = Query(...),
    lat: float = Query(...),
    distance_m: float = Query(5000, ge=MIN_DISTANCE_M, le=MAX_DISTANCE_M),
    pace_min_per_km: float = Query(DEFAULT_PACE_MIN_PER_KM, ge=MIN_PACE, le=MAX_PACE),
    hour: Optional[int] = Query(None, ge=0, le=23),
    index: int = Query(0, ge=0, le=5),
):
    prepared = _prepared()
    network, segments = prepared.network, prepared.segments
    candidates = generate_loops(
        network, segments, lon=lon, lat=lat, target_m=distance_m,
        pace_min_per_km=pace_min_per_km, hour=hour, limit=index + 1,
        baseline=prepared.baseline,
    )
    if index >= len(candidates):
        raise HTTPException(status_code=404, detail="No loop at that index.")
    loop = candidates[index]
    body = route_to_gpx(loop.coordinates(network), loop.exposure)
    return Response(
        content=body,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": 'attachment; filename="clean-air-loop.gpx"'},
    )


def _why_this_route(chosen, alternatives) -> List[str]:
    """Deterministic sentences from the comparison. No adjectives it cannot back."""
    lines = []
    mine = chosen.exposure.baseline_no2_mean
    others = [c.exposure.baseline_no2_mean for c in alternatives
              if c.exposure.baseline_no2_mean is not None]
    if mine is not None and others:
        best_other = min(others)
        delta = best_other - mine
        if delta >= 0.1:
            lines.append(
                f"Modelled annual-mean NO2 along this loop is {mine:.1f} ug/m3, "
                f"{delta:.1f} lower than the next candidate."
            )
        else:
            lines.append(
                f"All candidates sit within {max(others + [mine]) - min(others + [mine]):.1f} "
                f"ug/m3 of each other on modelled NO2. On air, this choice barely matters."
            )
    measured = chosen.exposure.mean_concentration
    share = chosen.exposure.measured_share
    if measured is not None:
        lines.append(
            f"Tram sensors measured {share * 100:.0f}% of this route, averaging "
            f"{measured:.1f} ug/m3 PM2.5 there in the 2019-20 campaign. That is a "
            f"historical record, not today's air, and the sensors disagree with "
            f"each other by more than streets differ - so it corroborates the "
            f"ranking rather than setting it."
        )
    else:
        lines.append(
            "No tram sensor ever passed this route. Unmeasured, which is not the "
            "same as clean."
        )
    lines.append(
        f"{(1 - share) * 100:.0f}% of the route has no measurement of any kind and "
        f"contributes nothing to the measured figure."
    )
    return lines


@router.get("/report")
def report(
    lon: float = Query(...),
    lat: float = Query(...),
    distance_m: float = Query(5000, ge=MIN_DISTANCE_M, le=MAX_DISTANCE_M),
    pace_min_per_km: float = Query(DEFAULT_PACE_MIN_PER_KM, ge=MIN_PACE, le=MAX_PACE),
    hour: Optional[int] = Query(None, ge=0, le=23),
    index: int = Query(0, ge=0, le=5),
    conditions: bool = Query(True, description="fetch weather, pollen and terrain"),
):
    """Everything shown before someone exports the GPX.

    One request rather than four, because the report is a single artefact and a
    half-loaded one would invite reading the air figure without its coverage.
    """
    prepared = _prepared()
    network, segments = prepared.network, prepared.segments
    candidates = generate_loops(
        network, segments, lon=lon, lat=lat, target_m=distance_m,
        pace_min_per_km=pace_min_per_km, hour=hour, limit=max(index + 1, 3),
        baseline=prepared.baseline,
    )
    if index >= len(candidates):
        raise HTTPException(status_code=404, detail="No loop at that index.")
    chosen = candidates[index]
    coordinates = chosen.coordinates(network)

    body = {
        "run": {
            "distance_km": round(chosen.distance_m / 1000.0, 2),
            "duration_min": round(chosen.exposure.minutes, 1),
            "pace_min_per_km": pace_min_per_km,
            "hour": hour,
        },
        "air": chosen.exposure.as_dict(),
        "why_this_route": _why_this_route(
            chosen, [c for i, c in enumerate(candidates) if i != index]
        ),
        "alternatives": [
            {
                "index": i,
                "distance_km": round(c.distance_m / 1000.0, 2),
                "baseline_no2": (
                    round(c.exposure.baseline_no2_mean, 1)
                    if c.exposure.baseline_no2_mean is not None else None
                ),
                "measured_pm25": (
                    round(c.exposure.mean_concentration, 2)
                    if c.exposure.mean_concentration is not None else None
                ),
                "measured_share": round(c.exposure.measured_share, 3),
            }
            for i, c in enumerate(candidates)
        ],
        "provenance": {
            "measured": prepared.source_provenance,
            "modelled": prepared.baseline_provenance,
            "network": prepared.network_note,
            "fixture_warning": prepared.source_note,
        },
    }
    if conditions:
        from .conditions import fetch_conditions, fetch_terrain

        body["conditions"] = fetch_conditions(lat, lon)
        body["terrain"] = fetch_terrain(coordinates)
    return body


@router.get("/conditions")
def conditions(
    lat: float = Query(...),
    lon: float = Query(...),
    hour_iso: Optional[str] = Query(None, description="e.g. 2026-09-03T18"),
):
    """Weather, European AQI and pollen for one point and hour.

    Its own endpoint because the planner shows it before anyone has chosen a
    route, and because a slow forecast service must not delay the routes.
    """
    from .conditions import fetch_conditions

    return fetch_conditions(lat, lon, hour_iso=hour_iso)


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def planner_page():
    """The runO2 interface."""
    from fastapi.responses import FileResponse

    from ..config import STATIC_DIR

    return FileResponse(STATIC_DIR / "run.html")
