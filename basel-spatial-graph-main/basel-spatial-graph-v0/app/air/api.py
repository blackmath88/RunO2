"""HTTP surface for the run planner.

Mounted as its own router so the existing API is untouched. Two endpoints:

    GET /run/loops    candidate loops for a pin, distance, pace and hour
    GET /run/gpx      the chosen loop as a GPX file with provenance extensions

Every loop response carries its coverage and its parameters, because a value
computed for one pace at one hour over 15% of the network is not a fact about
Basel and must not arrive looking like one.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .attribute import attribute_from_source
from .exposure import DEFAULT_PACE_MIN_PER_KM
from .gpx import route_to_gpx
from .loops import generate_loops
from .sources.fixture_source import FixtureAirSource

router = APIRouter(prefix="/run", tags=["run"])

MIN_DISTANCE_M, MAX_DISTANCE_M = 1000, 25000
MIN_PACE, MAX_PACE = 3.0, 12.0


@lru_cache(maxsize=1)
def _prepared():
    """Network plus attributed air, built once.

    Falls back to the fixture air field when no prepared readings exist, and
    the response says which one it used — a demo silently serving synthetic
    data as if it were measurements would undo the entire point.
    """
    try:
        from ..street_sources.graphml_cache import load_cached_network  # type: ignore

        network = load_cached_network("walk")
    except Exception:
        from .testing import fixture_network

        network = fixture_network()
    source = FixtureAirSource()
    segments, coverage = attribute_from_source(network, source)
    return network, segments, coverage, source


@router.get("/loops")
def loops(
    lon: float = Query(..., description="start longitude"),
    lat: float = Query(..., description="start latitude"),
    distance_m: float = Query(5000, ge=MIN_DISTANCE_M, le=MAX_DISTANCE_M),
    pace_min_per_km: float = Query(DEFAULT_PACE_MIN_PER_KM, ge=MIN_PACE, le=MAX_PACE),
    hour: Optional[int] = Query(None, ge=0, le=23),
    limit: int = Query(3, ge=1, le=6),
):
    network, segments, coverage, source = _prepared()
    candidates = generate_loops(
        network, segments, lon=lon, lat=lat, target_m=distance_m,
        pace_min_per_km=pace_min_per_km, hour=hour, limit=limit,
    )
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=(
                "No loop near that distance from this point. Try a different "
                "distance or a start closer to the network."
            ),
        )
    return {
        "loops": [c.as_dict(network) for c in candidates],
        "network_coverage": coverage.as_dict(),
        "air_source": {
            "mode": source.mode,
            "fixture": source.mode == "fixture",
            "warning": (
                "Synthetic air field — not measurements."
                if source.mode == "fixture" else None
            ),
        },
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
    network, segments, _, _ = _prepared()
    candidates = generate_loops(
        network, segments, lon=lon, lat=lat, target_m=distance_m,
        pace_min_per_km=pace_min_per_km, hour=hour, limit=index + 1,
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
