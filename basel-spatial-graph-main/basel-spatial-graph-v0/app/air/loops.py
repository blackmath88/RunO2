"""Candidate running loops from a start point and a distance target.

This is not an optimiser and does not pretend to be. True circuit generation
with a distance constraint is a hard problem and the one most likely to eat an
entire build window, so:

    pick waypoints on a circle around the start, route out and back through
    them, keep whatever lands near the target distance, score by exposure,
    return the best few.

The interface says "candidates", the code says candidates, and nobody is misled
about having been given an optimum. A better generator can replace this module
without touching anything else, because the only thing leaving here is a list
of node paths.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import networkx as nx

from .projection_compat import as_graph
from .exposure import DEFAULT_PACE_MIN_PER_KM, RouteExposure, score_path
from .model import SegmentAir

DEFAULT_BEARINGS = (0, 45, 90, 135, 180, 225, 270, 315)
DISTANCE_TOLERANCE = 0.25          # accept loops within +/-25% of the target


@dataclass
class LoopCandidate:
    nodes: List
    exposure: RouteExposure
    bearing: int

    @property
    def distance_m(self) -> float:
        return self.exposure.distance_m

    def coordinates(self, network) -> List[List[float]]:
        graph = as_graph(network)
        return [[graph.nodes[n]["lon"], graph.nodes[n]["lat"]] for n in self.nodes]

    def as_dict(self, network) -> dict:
        return {
            "bearing": self.bearing,
            "distance_km": round(self.distance_m / 1000.0, 2),
            "coordinates": self.coordinates(network),
            "exposure": self.exposure.as_dict(),
            "segments": [s.as_dict() for s in self.exposure.segments],
        }


def _nearest_node(network, lon: float, lat: float):
    from .projection_compat import to_metric

    graph = as_graph(network)
    (tx,), (ty,) = to_metric([lon], [lat])
    best, best_d = None, float("inf")
    for node, data in graph.nodes(data=True):
        if "x" not in data:
            continue
        d = math.hypot(data["x"] - tx, data["y"] - ty)
        if d < best_d:
            best, best_d = node, d
    return best


def _waypoint_node(network, lon: float, lat: float, bearing_deg: float, radius_m: float):
    """A node roughly `radius_m` away in a given compass direction."""
    lat_rad = math.radians(lat)
    dx = radius_m * math.sin(math.radians(bearing_deg))
    dy = radius_m * math.cos(math.radians(bearing_deg))
    target_lat = lat + dy / 111_132.0
    target_lon = lon + dx / (111_132.0 * math.cos(lat_rad))
    return _nearest_node(network, target_lon, target_lat)


def generate_loops(
    network,
    segments: Dict[str, SegmentAir],
    *,
    lon: float,
    lat: float,
    target_m: float = 5000.0,
    pace_min_per_km: float = DEFAULT_PACE_MIN_PER_KM,
    hour: Optional[int] = None,
    bearings: Sequence[int] = DEFAULT_BEARINGS,
    limit: int = 3,
    pollutant: str = "pm25",
    baseline: Optional[Dict[str, float]] = None,
) -> List[LoopCandidate]:
    """Return up to `limit` candidate loops, cleanest first."""
    graph = as_graph(network)
    start = _nearest_node(network, lon, lat)
    if start is None:
        return []

    # Out-and-back through one waypoint: the waypoint sits at roughly a quarter
    # of the target so the round trip lands near it.
    radius = target_m / 4.0
    candidates: List[LoopCandidate] = []
    seen = set()

    for bearing in bearings:
        waypoint = _waypoint_node(network, lon, lat, bearing, radius)
        if waypoint is None or waypoint == start:
            continue
        try:
            out_path = nx.shortest_path(graph, start, waypoint, weight="length_m")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        # Return leg via a second waypoint offset from the first, so the loop is
        # a loop rather than the same street twice.
        back_bearing = (bearing + 90) % 360
        second = _waypoint_node(network, lon, lat, back_bearing, radius * 0.7)
        legs = [out_path]
        if second is not None and second not in (start, waypoint):
            try:
                legs.append(nx.shortest_path(graph, waypoint, second, weight="length_m"))
                legs.append(nx.shortest_path(graph, second, start, weight="length_m"))
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                legs = [out_path, list(reversed(out_path))]
        else:
            legs.append(list(reversed(out_path)))

        nodes: List = []
        for leg in legs:
            nodes.extend(leg if not nodes else leg[1:])
        key = tuple(nodes)
        if key in seen:
            continue
        seen.add(key)

        exposure = score_path(
            network, nodes, segments, pace_min_per_km=pace_min_per_km,
            hour=hour, pollutant=pollutant, baseline=baseline,
        )
        if exposure.distance_m <= 0:
            continue
        if abs(exposure.distance_m - target_m) / target_m > DISTANCE_TOLERANCE:
            continue
        candidates.append(LoopCandidate(nodes=nodes, exposure=exposure, bearing=bearing))

    # What to rank on is a finding, not a preference.
    #
    # The tram measurements cannot separate these routes. Two sensors passing
    # the same street in the same hour disagree by 1.41 ug/m3 while two
    # different streets differ by 0.51 — see experiments/AIR_VIABILITY_REAL.md.
    # Ranking by them would be ranking noise while looking confident about it.
    #
    # The federal NO2 raster can: 3.0 ug/m3 between two streets, over 99.5% of
    # the network instead of 19%. So the ranking runs on the modelled baseline
    # where one exists, and the measured values are shown beside it as
    # corroboration rather than used as the deciding number.
    #
    # Without a baseline the old rule still applies, and a loop measured over
    # almost nothing still cannot win by being unknown.
    def rank(candidate: LoopCandidate):
        modelled = candidate.exposure.baseline_no2_mean
        if modelled is not None:
            return (0, modelled, -candidate.exposure.baseline_share)
        measured = candidate.exposure.mean_concentration
        return (1, measured if measured is not None else float("inf"),
                -candidate.exposure.measured_share)

    candidates.sort(key=rank)
    return candidates[:limit]
