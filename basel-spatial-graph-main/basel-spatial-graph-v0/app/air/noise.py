"""Is the street-to-street signal larger than the instrument's disagreement?

The coverage question ("how much of Basel was measured") and the spatial
question ("do streets differ") are not the only gates. A third one decides
whether a route recommendation can mean anything at all:

    When two sensors pass the same street in the same hour, how far apart are
    they? And is that smaller or larger than the difference between streets?

If two instruments disagree by as much as two streets differ, then ranking
routes by measured concentration is ranking noise, however many readings back
it. Coverage can be fixed by adding trams. This cannot.

Three steps, each one removing a confound the previous number still contained:

  1. `citywide_background` — the median of everything the fleet read in one
     clock hour, anywhere. Day-to-day weather moves every street together, so
     it belongs in neither the signal nor the noise.
  2. `street_contrast` — how far apart two streets typically are, once that
     common movement is removed.
  3. `sensor_disagreement` — how far apart two sensors typically are on the
     same street in the same hour, where the air is as close to identical as
     this data can make it.

Both (2) and (3) are reported as the median absolute difference between two
randomly chosen members, so they are the same statistic and can be divided.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .attribute import DEFAULT_RADIUS_M, _segment_midpoints
from .model import AirReading
from .projection_compat import to_metric

MIN_READINGS_PER_BIN = 30      # below this a citywide median is itself noise
MIN_READINGS_PER_CELL = 3      # one sensor's value for one street in one hour
PAIR_SAMPLE = 200_000          # enough for a stable median, cheap to compute


def citywide_background(
    readings: Sequence[AirReading], *, pollutant: str = "pm25",
    min_per_bin: int = MIN_READINGS_PER_BIN,
) -> Dict[Tuple[object, int], float]:
    """Median across the whole fleet per (date, hour).

    This is the part of a reading that says *when* rather than *where*.
    """
    bins: Dict[Tuple[object, int], List[float]] = defaultdict(list)
    for reading in readings:
        if pollutant in reading.values:
            bins[(reading.timestamp.date(), reading.timestamp.hour)].append(
                reading.values[pollutant]
            )
    return {
        key: float(np.median(values))
        for key, values in bins.items()
        if len(values) >= min_per_bin
    }


def as_enhancement(
    readings: Sequence[AirReading], background: Dict[Tuple[object, int], float],
    *, pollutant: str = "pm25",
) -> List[AirReading]:
    """Each reading minus the citywide level at that moment.

    What remains is the street's own contribution: positive where this place is
    dirtier than Basel was that hour, negative where it is cleaner. Readings in
    hours too sparse to establish a background are dropped rather than guessed.
    """
    out: List[AirReading] = []
    for reading in readings:
        if pollutant not in reading.values:
            continue
        level = background.get((reading.timestamp.date(), reading.timestamp.hour))
        if level is None:
            continue
        out.append(
            AirReading(
                lon=reading.lon, lat=reading.lat, timestamp=reading.timestamp,
                values={pollutant: reading.values[pollutant] - level},
                sensor_id=reading.sensor_id, provenance=reading.provenance,
            )
        )
    return out


def _median_pairwise_gap(values: Sequence[float], *, seed: int = 0) -> Optional[float]:
    """Median |a - b| over random pairs — the typical distance between two members."""
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    n = len(values)
    pairs = min(PAIR_SAMPLE, n * (n - 1) // 2)
    gaps = [
        abs(values[i] - values[j])
        for i, j in (
            (rng.randrange(n), rng.randrange(n)) for _ in range(pairs)
        )
        if i != j
    ]
    return float(np.median(gaps)) if gaps else None


def street_contrast(segments: Dict[str, object], *, hour: Optional[int] = 8) -> dict:
    """How far apart two streets typically are, in enhancement terms."""
    if hour is None:
        levels = [s.median for s in segments.values() if s.known]
        basis = "all hours pooled"
    else:
        levels = [s.by_hour[hour] for s in segments.values() if hour in s.by_hour]
        basis = f"hour {hour}"
    gap = _median_pairwise_gap(levels)
    return {
        "basis": basis,
        "segments_compared": len(levels),
        "median_gap_between_two_streets": round(gap, 2) if gap is not None else None,
        "unit": "ug/m3 (enhancement over citywide level)",
    }


def sensor_disagreement(
    network, readings: Sequence[AirReading], *, pollutant: str = "pm25",
    radius_m: float = DEFAULT_RADIUS_M, min_per_cell: int = MIN_READINGS_PER_CELL,
) -> dict:
    """How far apart two sensors are on the same street in the same hour.

    Same place, same clock hour: whatever is left is the instrument, plus the
    minutes between the two trams passing. It is an upper bound on agreement
    and therefore a lower bound on how large a real difference has to be before
    this data can see it.
    """
    ids, seg_x, seg_y, _ = _segment_midpoints(network)
    usable = [r for r in readings if pollutant in r.values]
    if not ids or not usable:
        return {"cells_compared": 0, "median_gap_between_two_sensors": None}

    rx, ry = to_metric([r.lon for r in usable], [r.lat for r in usable])
    rx = np.atleast_1d(np.asarray(rx, dtype=float))
    ry = np.atleast_1d(np.asarray(ry, dtype=float))

    cell_size = max(float(radius_m), 1.0)
    cells: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for col, (x, y) in enumerate(zip(seg_x, seg_y)):
        cells[(int(np.floor(x / cell_size)), int(np.floor(y / cell_size)))].append(col)

    # (segment, date, hour) -> sensor -> readings
    per: Dict[Tuple[str, object, int], Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    radius_sq = radius_m * radius_m
    for reading, x, y in zip(usable, rx, ry):
        cx, cy = int(np.floor(x / cell_size)), int(np.floor(y / cell_size))
        when = (reading.timestamp.date(), reading.timestamp.hour)
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for col in cells.get((gx, gy), ()):
                    if (x - seg_x[col]) ** 2 + (y - seg_y[col]) ** 2 > radius_sq:
                        continue
                    per[(ids[col], *when)][reading.sensor_id].append(
                        reading.values[pollutant]
                    )

    gaps: List[float] = []
    offsets: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for by_sensor in per.values():
        solid = {
            sensor: float(np.median(values))
            for sensor, values in by_sensor.items()
            if len(values) >= min_per_cell
        }
        if len(solid) < 2:
            continue
        gaps.append(max(solid.values()) - min(solid.values()))
        ordered = sorted(solid.items())
        for i, (a, va) in enumerate(ordered):
            for b, vb in ordered[i + 1:]:
                offsets[(a, b)].append(va - vb)

    if not gaps:
        return {"cells_compared": 0, "median_gap_between_two_sensors": None}
    return {
        "cells_compared": len(gaps),
        "cell_definition": "one segment, one date, one clock hour",
        "median_gap_between_two_sensors": round(float(np.median(gaps)), 2),
        "p90_gap": round(float(np.percentile(gaps, 90)), 2),
        "unit": "ug/m3",
        "systematic_offsets": [
            {
                "pair": f"{a} - {b}",
                "comparisons": len(values),
                "median_offset": round(float(np.median(values)), 2),
            }
            for (a, b), values in sorted(offsets.items(), key=lambda kv: -len(kv[1]))
            if len(values) >= 100
        ],
    }


def signal_to_noise(network, readings, *, pollutant: str = "pm25") -> dict:
    """The decisive comparison: street-to-street signal over instrument noise.

    Above 1, two streets differ by more than two instruments do, and a ranking
    can mean something. At or below 1, the recommendation is noise no matter
    how confident the interface looks.
    """
    from .attribute import attribute_readings

    background = citywide_background(readings, pollutant=pollutant)
    enhanced = as_enhancement(readings, background, pollutant=pollutant)
    segments, _ = attribute_readings(network, enhanced, pollutant=pollutant)

    contrast = street_contrast(segments)
    noise = sensor_disagreement(network, readings, pollutant=pollutant)
    signal = contrast["median_gap_between_two_streets"]
    floor = noise["median_gap_between_two_sensors"]
    ratio = (signal / floor) if (signal and floor) else None

    levels = list(background.values())
    return {
        "citywide_background": {
            "bins": len(background),
            "bin_definition": "one date, one clock hour, whole fleet",
            "p10": round(float(np.percentile(levels, 10)), 2) if levels else None,
            "median": round(float(np.median(levels)), 2) if levels else None,
            "p90": round(float(np.percentile(levels, 90)), 2) if levels else None,
            "note": (
                "Day-to-day variation moves every street together. It is removed "
                "from both sides of the comparison below."
            ),
        },
        "signal_street_contrast": contrast,
        "noise_sensor_disagreement": noise,
        "signal_to_noise_ratio": round(ratio, 2) if ratio else None,
        # None, not False: with one sensor per street nothing can be compared,
        # and an unmeasurable gate must not condemn the dataset the way a
        # failed one does. Unknown is not bad, here as everywhere else.
        "passes": None if ratio is None else bool(ratio >= 1.0),
        "threshold": 1.0,
        "interpretation": (
            "No street was visited by two different sensors in the same hour, so "
            "the instruments were never compared with each other. This gate is "
            "undetermined, not passed."
            if ratio is None else
            "Two streets differ by more than two sensors do. A ranking can carry "
            "information."
            if ratio >= 1.0 else
            "Two sensors on the same street in the same hour disagree by as much "
            "as two different streets do. Ranking routes by these values ranks "
            "noise. More trams would add coverage, not resolution — only "
            "calibration against reference instruments would."
        ),
    }
