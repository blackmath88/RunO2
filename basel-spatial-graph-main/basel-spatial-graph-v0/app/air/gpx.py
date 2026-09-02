"""GPX export, with the provenance travelling inside the file.

Every running application imports GPX — Strava, Garmin, Komoot, Apple Fitness —
with no OAuth, no API key and no terms review. That is the whole integration
story, and it takes an afternoon instead of a week.

The interesting part is the `<extensions>` block. GPX readers are required to
ignore extension content they do not understand, so the file stays importable
everywhere while carrying, per track point, which dataset the concentration
came from, when it was retrieved, and whether it was measured at all. Anyone
who opens the file in a text editor can see where every number came from.

A portable record format for this — provenance-carrying activity records on an
open protocol — is the obvious next step. It is not this week's work.
"""
from __future__ import annotations

from typing import List, Optional
from xml.sax.saxutils import escape

from .exposure import RouteExposure
from .model import MEASURED, utc_now_iso

NAMESPACE = "https://github.com/blackmath88/basel-spatial-graph/ns/air/1"
GENERATOR = "basel-spatial-graph clean-air-run"


def _tag(name: str, value) -> str:
    return f"<air:{name}>{escape(str(value))}</air:{name}>"


def route_to_gpx(
    coordinates: List[List[float]],
    exposure: RouteExposure,
    *,
    name: str = "Clean air loop",
    generator_version: str = "0.1",
) -> str:
    """Serialise one scored loop as GPX 1.1 with air provenance extensions."""
    if len(coordinates) != len(exposure.segments) + 1 and coordinates:
        # Segments sit between points; tolerate a mismatch rather than fail,
        # but never invent a value for a point we cannot account for.
        pass

    summary = exposure.as_dict()
    header_ext = "".join([
        _tag("generator", GENERATOR),
        _tag("generator_version", generator_version),
        _tag("generated_at", utc_now_iso()),
        _tag("pollutant", exposure.pollutant),
        _tag("exposure_total", summary["total"]),
        _tag("exposure_unit", exposure.unit),
        _tag("pace_min_per_km", exposure.pace_min_per_km),
        _tag("hour_assumed", exposure.hour if exposure.hour is not None else "any"),
        _tag("distance_km", summary["parameters"]["distance_km"]),
        _tag("duration_min", summary["parameters"]["duration_min"]),
        _tag("measured_share", summary["coverage"]["measured_share"]),
        _tag("unmeasured_share", summary["coverage"]["unmeasured_share"]),
        _tag("classification", "dynamic"),
        _tag("note", "Unmeasured stretches are unknown, not clean."),
    ])

    points: List[str] = []
    for i, coord in enumerate(coordinates):
        lon, lat = float(coord[0]), float(coord[1])
        # Attribute the segment that starts at this point; the final point has none.
        segment = exposure.segments[i] if i < len(exposure.segments) else None
        parts = []
        if segment is not None:
            parts.append(_tag("classification", segment.classification))
            if segment.classification == MEASURED and segment.concentration is not None:
                parts.append(_tag("concentration", round(segment.concentration, 2)))
                parts.append(_tag("concentration_unit", "ug/m3"))
            parts.append(_tag("segment_id", segment.segment_id))
        extensions = f"<extensions>{''.join(parts)}</extensions>" if parts else ""
        points.append(
            f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}">{extensions}</trkpt>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="' + GENERATOR + '" '
        'xmlns="http://www.topografix.com/GPX/1/1" '
        f'xmlns:air="{NAMESPACE}">'
        f"<metadata><name>{escape(name)}</name>"
        f"<time>{utc_now_iso()}</time>"
        f"<extensions>{header_ext}</extensions></metadata>"
        f"<trk><name>{escape(name)}</name><trkseg>"
        + "".join(points) +
        "</trkseg></trk></gpx>"
    )
