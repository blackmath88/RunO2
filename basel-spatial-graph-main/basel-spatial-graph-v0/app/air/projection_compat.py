"""Metric projection, with a dependency-free fallback.

The repository projects through pyproj. The air package is also used by the
viability script, which people may run in a bare environment before installing
anything, so a local equirectangular approximation stands in when pyproj is
absent. It is accurate to well under a metre across a city and is only ever
used for distances of tens of metres.
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

BASEL_LAT = 47.5596
_M_PER_DEG_LAT = 111_132.0


def _fallback(lons: Sequence[float], lats: Sequence[float]) -> Tuple[list, list]:
    scale = math.cos(math.radians(BASEL_LAT))
    xs = [lon * _M_PER_DEG_LAT * scale for lon in lons]
    ys = [lat * _M_PER_DEG_LAT for lat in lats]
    return xs, ys


try:  # pragma: no cover - exercised implicitly by the repo's own test suite
    from ..projection import to_metric  # type: ignore
except Exception:  # pragma: no cover
    to_metric = _fallback  # type: ignore


def as_graph(network):
    """Accept either a StreetNetwork wrapper or a bare networkx graph.

    Note: a networkx Graph *has* a `.graph` attribute (its metadata dict), so
    duck-typing on that name silently returns a dict. Check for edges instead.
    """
    return network if hasattr(network, "edges") else network.graph
