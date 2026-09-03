"""The gate. Run this before building anything on top of the air data.

Three questions, answered with numbers rather than hope:

  1. spatial   Does the median differ enough between segments to make a route
               choice meaningful, compared with the spread of readings at the
               same place?
  2. temporal  Do segment *rankings* change by hour, or is it one fixed pattern
               moving up and down together? Only the former justifies an
               hour-of-day control.
  3. coverage  What share of the walking network is within 50m of any reading?

A failing answer is a good outcome, not a wasted evening. It is cheaper to
learn in an hour that the data cannot carry a route recommendation than to
discover it after building an interface around one.

    python -m app.air.viability --csv path/to/tram_readings.csv
    python -m app.air.viability --fixture          # exercise the code path
"""
from __future__ import annotations

import argparse
import json
import statistics
from typing import Dict, Optional

import numpy as np

from .attribute import attribute_from_source
from .model import SegmentAir
from .noise import signal_to_noise

# A route choice is only meaningful if between-street differences are large
# next to within-street variability.
MIN_SPREAD_RATIO = 1.5
MIN_RANK_CHANGE = 0.25       # Spearman-style disagreement between hours


def _percentile_gap(segments: Dict[str, SegmentAir], reference_hour: int = 8) -> Optional[dict]:
    """Do streets differ from each other by more than readings differ at one street?

    Both sides of that comparison are taken at a single hour. Pooling across the
    day would fold the morning-to-evening swing into the within-street spread,
    which makes genuine street-to-street differences look like noise and would
    fail a dataset that is in fact usable.
    """
    at_hour = [(s.by_hour[reference_hour], s.by_hour_p90.get(reference_hour))
               for s in segments.values() if reference_hour in s.by_hour]
    if len(at_hour) >= 10:
        medians = [v for v, _ in at_hour]
        within = [p90 - v for v, p90 in at_hour if p90 is not None]
        basis = f"hour {reference_hour}"
    else:                                    # not enough hourly data; pool, and say so
        medians = [s.median for s in segments.values() if s.known]
        within = [s.p90 - s.median for s in segments.values() if s.known and s.p90 is not None]
        basis = "all hours pooled (hourly data too sparse)"
    if len(medians) < 10:
        return None

    low, high = float(np.percentile(medians, 10)), float(np.percentile(medians, 90))
    typical_within = float(np.median(within)) if within else 0.0
    ratio = (high - low) / typical_within if typical_within > 0 else float("inf")
    return {
        "basis": basis,
        "segments_compared": len(medians),
        "p10": round(low, 2),
        "p90": round(high, 2),
        "between_street_gap": round(high - low, 2),
        "typical_within_street_spread": round(typical_within, 2),
        "ratio": round(ratio, 2) if ratio != float("inf") else None,
        "passes": ratio >= MIN_SPREAD_RATIO,
        "threshold": MIN_SPREAD_RATIO,
    }


def _rank_flip(segments: Dict[str, SegmentAir], morning: int = 8, evening: int = 17) -> Optional[dict]:
    pairs = [
        (s.by_hour.get(morning), s.by_hour.get(evening))
        for s in segments.values()
        if s.by_hour.get(morning) is not None and s.by_hour.get(evening) is not None
    ]
    if len(pairs) < 10:
        return None
    m = np.array([p[0] for p in pairs])
    e = np.array([p[1] for p in pairs])
    rank_m = np.argsort(np.argsort(m))
    rank_e = np.argsort(np.argsort(e))
    n = len(pairs)
    # Spearman correlation without scipy.
    d2 = float(np.sum((rank_m - rank_e) ** 2))
    rho = 1 - (6 * d2) / (n * (n * n - 1))
    disagreement = (1 - rho) / 2
    return {
        "segments_compared": n,
        "morning_hour": morning,
        "evening_hour": evening,
        "rank_correlation": round(float(rho), 3),
        "disagreement": round(float(disagreement), 3),
        "passes": disagreement >= MIN_RANK_CHANGE,
        "threshold": MIN_RANK_CHANGE,
        "interpretation": (
            "Rankings change by hour — an hour-of-day control is justified."
            if disagreement >= MIN_RANK_CHANGE
            else "One pattern moving up and down. Drop the hour strip and simplify."
        ),
    }


def run(network, source, *, pollutant: str = "pm25", with_resolution: bool = True) -> dict:
    readings = source.readings()
    from .attribute import attribute_readings

    segments, coverage = attribute_readings(
        network, readings, pollutant=pollutant,
        error_band=source.error_band(pollutant),
    )
    spatial = _percentile_gap(segments)
    temporal = _rank_flip(segments)
    resolution = signal_to_noise(network, readings, pollutant=pollutant) if with_resolution else None
    verdict = {
        "pollutant": pollutant,
        "spatial": spatial,
        "temporal": temporal,
        "coverage": coverage.as_dict(),
    }
    if resolution is not None:
        verdict["resolution"] = resolution
    # Resolution is the binding gate. A dataset can pass the percentile check
    # because day-to-day weather widens the spread of street medians, and still
    # be unable to tell two streets apart on any single morning.
    gates = [
        spatial and spatial["passes"],
        coverage.segment_share > 0.05,
        # An undetermined resolution gate (None) does not block; a failed one does.
        resolution["passes"] is not False if resolution is not None else True,
    ]
    verdict["route_recommendation_viable"] = all(bool(g) for g in gates)
    verdict["hour_control_viable"] = bool(temporal and temporal["passes"])
    return verdict


def _markdown(verdict: dict, data_statistics: Optional[dict] = None,
              provenance: Optional[dict] = None) -> str:
    lines = ["# Air data viability", ""]
    if provenance:
        # A verdict about a dataset is worthless without saying which dataset,
        # which copy of it, and when that copy was taken.
        lines.append("| | |")
        lines.append("|---|---|")
        for label, key in (
            ("Dataset", "dataset"), ("Title", "dataset_title"),
            ("Source", "source"), ("Licence", "license"),
            ("Retrieved", "retrieved_at"), ("Publisher last update", "source_last_update"),
            ("Sensor class", "sensor_class"),
        ):
            value = provenance.get(key)
            if value:
                lines.append(f"| {label} | {value} |")
        lines.append("")
    lines.append(f"Pollutant: `{verdict['pollutant']}`")
    lines.append("")
    lines.append(f"**Route recommendation viable:** {verdict['route_recommendation_viable']}")
    lines.append(f"**Hour-of-day control viable:** {verdict['hour_control_viable']}")
    lines.append("")
    for key in ("spatial", "temporal", "coverage", "resolution"):
        if key not in verdict:
            continue
        lines.append(f"## {key}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(verdict[key], indent=2))
        lines.append("```")
        lines.append("")
    if data_statistics:
        lines.extend([
            "## measurement window",
            "",
            "```json",
            json.dumps(data_statistics, indent=2),
            "```",
            "",
        ])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="path to the tram readings export")
    parser.add_argument("--fixture", action="store_true", help="use the synthetic field")
    parser.add_argument("--pollutant", default="pm25")
    parser.add_argument("--skip-resolution", action="store_true",
                        help="omit the signal-vs-noise gate (it re-reads every reading)")
    parser.add_argument("--out", default="experiments/AIR_VIABILITY.md")
    args = parser.parse_args(argv)

    from .sources import BaselTramAirSource, FixtureAirSource
    from .testing import fixture_network

    if args.csv:
        source = BaselTramAirSource(args.csv)
        from ..street_sources import load_network
        network = load_network("walk")
    else:
        source = FixtureAirSource()
        network = fixture_network()

    verdict = run(network, source, pollutant=args.pollutant,
                  with_resolution=not args.skip_resolution)
    first = next(iter(source.readings()), None)
    text = _markdown(verdict, getattr(source, "statistics", None),
                     dict(first.provenance) if first else None)
    print(text)
    try:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"\nwritten to {args.out}")
    except OSError as exc:
        print(f"\ncould not write {args.out}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
