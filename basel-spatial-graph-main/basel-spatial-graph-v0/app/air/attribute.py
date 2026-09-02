"""Join readings to street segments — and account for what stays unjoined.

A reading is attributed to every street segment whose midpoint lies within
`radius_m`. That is deliberately crude: the sensor is on a tram roof, the tram
is on rails, and pretending we know the concentration 40 metres away on a
parallel side street to any better precision would be false precision.

The output is one `SegmentAir` per segment in the network — including segments
with no readings at all, which come back with `reading_count == 0` and
classification `unmeasured`. Nothing is dropped, because a missing key in a
dict is how "we don't know" quietly becomes "it's fine".
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .projection_compat import as_graph
from .model import AirReading, Coverage, SegmentAir
from .sources.base import AirSource

DEFAULT_RADIUS_M = 50.0
MIN_READINGS_FOR_HOUR = 8      # below this, an hourly median is noise


def segment_id(u, v) -> str:
    """Stable, order-independent id for an undirected edge."""
    a, b = sorted((str(u), str(v)))
    return f"{a}|{b}"


def _segment_midpoints(network) -> Tuple[List[str], np.ndarray, np.ndarray, np.ndarray]:
    """Metric midpoints of every edge, plus lengths."""
    ids, xs, ys, lengths = [], [], [], []
    graph = as_graph(network)
    for u, v, data in graph.edges(data=True):
        nu, nv = graph.nodes[u], graph.nodes[v]
        if "x" not in nu or "x" not in nv:
            continue
        ids.append(segment_id(u, v))
        xs.append((nu["x"] + nv["x"]) / 2.0)
        ys.append((nu["y"] + nv["y"]) / 2.0)
        lengths.append(float(data.get("length_m", 0.0)))
    return ids, np.asarray(xs), np.asarray(ys), np.asarray(lengths)


def attribute_readings(
    network,
    readings: Sequence[AirReading],
    *,
    pollutant: str = "pm25",
    radius_m: float = DEFAULT_RADIUS_M,
    error_band: Optional[float] = None,
    with_hours: bool = True,
) -> Tuple[Dict[str, SegmentAir], Coverage]:
    from .projection_compat import to_metric

    ids, seg_x, seg_y, lengths = _segment_midpoints(network)
    if not ids:
        return {}, Coverage(0, 0, 0.0, 0.0)

    usable = [r for r in readings if pollutant in r.values]
    buckets: Dict[str, List[float]] = defaultdict(list)
    hour_buckets: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    provenance_by_segment: Dict[str, dict] = {}

    if usable:
        rx, ry = to_metric([r.lon for r in usable], [r.lat for r in usable])
        rx = np.atleast_1d(np.asarray(rx, dtype=float))
        ry = np.atleast_1d(np.asarray(ry, dtype=float))
        # A radius-sized spatial grid keeps the real 600k-reading dataset
        # linear. Each reading only checks segments in its own and eight
        # neighbouring cells; the distance test remains exactly the same.
        cell_size = max(float(radius_m), 1.0)
        cells: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for col, (x, y) in enumerate(zip(seg_x, seg_y)):
            cells[(int(np.floor(x / cell_size)), int(np.floor(y / cell_size)))].append(col)
        radius_sq = radius_m * radius_m
        for reading, x, y in zip(usable, rx, ry):
            cx, cy = int(np.floor(x / cell_size)), int(np.floor(y / cell_size))
            for gx in range(cx - 1, cx + 2):
                for gy in range(cy - 1, cy + 2):
                    for col in cells.get((gx, gy), ()):
                        if (x - seg_x[col]) ** 2 + (y - seg_y[col]) ** 2 > radius_sq:
                            continue
                        sid = ids[col]
                        buckets[sid].append(reading.values[pollutant])
                        if with_hours:
                            hour_buckets[sid][reading.hour].append(reading.values[pollutant])
                        provenance_by_segment.setdefault(sid, reading.provenance or {})

    segments: Dict[str, SegmentAir] = {}
    for i, sid in enumerate(ids):
        values = buckets.get(sid, [])
        by_hour, by_hour_p90 = {}, {}
        if with_hours and values:
            for hour, hour_values in hour_buckets[sid].items():
                if len(hour_values) >= MIN_READINGS_FOR_HOUR:
                    by_hour[int(hour)] = float(np.median(hour_values))
                    by_hour_p90[int(hour)] = float(np.percentile(hour_values, 90))
        segments[sid] = SegmentAir(
            segment_id=sid,
            pollutant=pollutant,
            median=float(np.median(values)) if values else None,
            p90=float(np.percentile(values, 90)) if values else None,
            reading_count=len(values),
            by_hour=by_hour,
            by_hour_p90=by_hour_p90,
            error_band=error_band,
            provenance=provenance_by_segment.get(sid, {}),
        )

    measured_mask = np.array([segments[sid].reading_count > 0 for sid in ids])
    coverage = Coverage(
        segments_total=len(ids),
        segments_measured=int(measured_mask.sum()),
        network_length_m=float(lengths.sum()),
        measured_length_m=float(lengths[measured_mask].sum()) if len(lengths) else 0.0,
    )
    return segments, coverage


def attribute_from_source(network, source: AirSource, *, pollutant: str = "pm25", **kwargs):
    """Convenience: pull readings and their error band from one source."""
    return attribute_readings(
        network,
        source.readings(),
        pollutant=pollutant,
        error_band=source.error_band(pollutant),
        **kwargs,
    )
