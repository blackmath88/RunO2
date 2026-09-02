"""Turning concentrations into an exposure estimate for one run.

Exposure is concentration multiplied by the volume of air breathed, and the
volume depends on how long you are out there. That is the one line of
arithmetic a normal running app does not do, and it is why pace belongs in this
model rather than only in the display:

    exposure = sum over segments of  concentration * minutes_on_segment * ventilation

`ventilation` is a single constant, not a physiological model. A runner moves
roughly ten times the air per minute of someone sitting still, which is why the
route matters more for them than for anyone else; putting a precise number on
one person's intake would be a claim this data cannot support.

Unmeasured segments contribute nothing to the total and everything to the
caveat: their share of the route travels with the result, so a total computed
over 20% of a loop can never be displayed as if it covered all of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .projection_compat import as_graph
from .attribute import segment_id
from .model import MEASURED, UNMEASURED, SegmentAir

# Litres of air per minute, running. Round number, deliberately.
VENTILATION_L_PER_MIN = 60.0
DEFAULT_PACE_MIN_PER_KM = 6.0


@dataclass
class SegmentExposure:
    segment_id: str
    length_m: float
    minutes: float
    concentration: Optional[float]
    classification: str
    contribution: float = 0.0

    def as_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "length_m": round(self.length_m, 1),
            "minutes": round(self.minutes, 2),
            "concentration": round(self.concentration, 2) if self.concentration is not None else None,
            "classification": self.classification,
            "contribution": round(self.contribution, 1),
        }


@dataclass
class RouteExposure:
    """The dynamic value. Meaningless without its parameters, so it carries them."""

    total: float
    unit: str = "ug-minutes (indicative)"
    distance_m: float = 0.0
    minutes: float = 0.0
    pace_min_per_km: float = DEFAULT_PACE_MIN_PER_KM
    hour: Optional[int] = None
    pollutant: str = "pm25"
    measured_length_m: float = 0.0
    segments: List[SegmentExposure] = field(default_factory=list)

    @property
    def measured_share(self) -> float:
        return self.measured_length_m / self.distance_m if self.distance_m else 0.0

    @property
    def mean_concentration(self) -> Optional[float]:
        """Average over the measured part only, which is the honest denominator."""
        measured = [s for s in self.segments if s.classification == MEASURED and s.minutes > 0]
        minutes = sum(s.minutes for s in measured)
        if not minutes:
            return None
        return sum(s.concentration * s.minutes for s in measured) / minutes

    def as_dict(self) -> dict:
        return {
            "classification": "dynamic",
            "explanation": (
                "Computed for this request from these parameters. A different "
                "pace or hour gives a different number."
            ),
            "total": round(self.total, 1),
            "unit": self.unit,
            "mean_concentration": (
                round(self.mean_concentration, 2) if self.mean_concentration is not None else None
            ),
            "concentration_unit": "ug/m3",
            "pollutant": self.pollutant,
            "parameters": {
                "pace_min_per_km": self.pace_min_per_km,
                "hour": self.hour,
                "distance_km": round(self.distance_m / 1000.0, 2),
                "duration_min": round(self.minutes, 1),
            },
            "coverage": {
                "measured_share": round(self.measured_share, 3),
                "unmeasured_share": round(1.0 - self.measured_share, 3),
                "note": (
                    "Unmeasured stretches contribute nothing to the total. "
                    "They are unknown, not clean."
                ),
            },
        }


def duration_minutes(distance_m: float, pace_min_per_km: float) -> float:
    return (distance_m / 1000.0) * pace_min_per_km


def score_path(
    network,
    path_nodes: Sequence,
    segments: Dict[str, SegmentAir],
    *,
    pace_min_per_km: float = DEFAULT_PACE_MIN_PER_KM,
    hour: Optional[int] = None,
    pollutant: str = "pm25",
) -> RouteExposure:
    """Exposure for one ordered list of nodes."""
    graph = as_graph(network)
    out: List[SegmentExposure] = []
    total = distance = measured_length = 0.0

    for u, v in zip(path_nodes, path_nodes[1:]):
        data = graph.get_edge_data(u, v)
        if data is None:
            continue
        if isinstance(data, dict) and 0 in data:      # MultiGraph
            data = data[0]
        length = float(data.get("length_m", 0.0))
        sid = segment_id(u, v)
        air = segments.get(sid)
        minutes = duration_minutes(length, pace_min_per_km)
        concentration = air.value_at_hour(hour) if air else None
        classification = MEASURED if concentration is not None else UNMEASURED
        contribution = 0.0
        if concentration is not None:
            contribution = concentration * minutes * (VENTILATION_L_PER_MIN / 1000.0)
            measured_length += length
        total += contribution
        distance += length
        out.append(SegmentExposure(sid, length, minutes, concentration, classification, contribution))

    return RouteExposure(
        total=total,
        distance_m=distance,
        minutes=duration_minutes(distance, pace_min_per_km),
        pace_min_per_km=pace_min_per_km,
        hour=hour,
        pollutant=pollutant,
        measured_length_m=measured_length,
        segments=out,
    )
