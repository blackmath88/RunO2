"""A synthetic air field with a known shape, so tests assert against truth.

The fixture deliberately builds in the two things the viability check looks
for in the real data:

  * a spatial gradient — a "corridor" of high readings across the middle of the
    bounding box, so route choice can measurably matter;
  * an hour-of-day inversion — the corridor is worst in the morning while the
    edges are worst in the late afternoon, so segment *rankings* flip rather
    than the whole field moving up and down together.

Building the inversion into the fixture is not a claim that Basel's air does
this. It is so that the code path which detects an inversion has something to
detect, and so the interface can be developed before the real answer is known.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..model import AirReading
from .base import FIXTURE, AirSource, make_air_provenance

# Roughly central Basel, matching the fixture bounding box used elsewhere.
DEFAULT_BBOX = (7.575, 47.545, 7.615, 47.570)   # west, south, east, north
BASE_PM25 = 8.0
CORRIDOR_PEAK = 14.0
EDGE_PEAK = 6.0


class FixtureAirSource(AirSource):
    mode = FIXTURE

    def __init__(self, bbox=DEFAULT_BBOX, days: int = 3, step_minutes: int = 15,
                 seed: int = 7, grid=(10, 12)):
        self.bbox = bbox
        self.grid = grid   # must match app.air.testing.fixture_network
        self.days = days
        self.step_minutes = step_minutes
        self.seed = seed

    def error_band(self, pollutant: str) -> Optional[float]:
        # Stand-in for the published comparison figure. Fixture, not a claim.
        return 3.0 if pollutant == "pm25" else 5.0

    def readings(self) -> List[AirReading]:
        """Readings along three east-west lines, sampled every `step_minutes`.

        The lines are placed on rows of the fixture grid so that attribution
        actually lands on segments, and the concentration field varies with
        *both* longitude and latitude — a hotspot rather than a stripe. A field
        varying in one axis only would give every segment on a line the same
        value, and the spatial check would correctly report no signal.
        """
        west, south, east, north = self.bbox
        mid_lat = (south + north) / 2.0
        mid_lon = (west + east) / 2.0
        provenance = make_air_provenance(
            mode=FIXTURE,
            source="fixture",
            dataset="fixture:air",
            dataset_title="Synthetic air field (deterministic fixture)",
            license="n/a",
            sensor_class="fixture",
        )
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        out: List[AirReading] = []
        steps_per_day = int(24 * 60 / self.step_minutes)
        # Sensor lines sit exactly on rows of the fixture grid (rows 2, 4, 6 of
        # 10) and sample at every column, so readings land on real segments.
        rows, cols = self.grid
        lines = [(r, south + (north - south) * (r / (rows - 1))) for r in (2, 4, 6)]
        for day in range(self.days):
            for step in range(steps_per_day):
                stamp = start + timedelta(days=day, minutes=step * self.step_minutes)
                hour = stamp.hour
                morning = math.exp(-((hour - 8) ** 2) / 8.0)
                evening = math.exp(-((hour - 17) ** 2) / 8.0)
                for row, lat in lines:
                    # Sample twice per grid interval: a tram reads continuously
                    # along the line, so midpoints of segments get readings too.
                    samples = 2 * (cols - 1) + 1
                    for i in range(samples):
                        lon = west + (east - west) * (i / (samples - 1))
                        # Distance from the city-centre hotspot, in both axes.
                        dy = abs(lat - mid_lat) / max(north - mid_lat, 1e-9)
                        dx = abs(lon - mid_lon) / max(east - mid_lon, 1e-9)
                        centre = max(0.0, 1.0 - math.hypot(dx, dy) / 1.4142)
                        edge = 1.0 - centre
                        # Morning loads the centre; late afternoon loads the edges,
                        # so segment rankings flip rather than merely rising.
                        value = (
                            BASE_PM25
                            + CORRIDOR_PEAK * centre * morning
                            + EDGE_PEAK * edge * evening
                        )
                        # Deterministic jitter, no RNG state to leak between tests.
                        jitter = 0.15 * math.sin(self.seed * (i + 1) * (row + 1) + step)
                        out.append(
                            AirReading(
                                lon=lon,
                                lat=lat,
                                timestamp=stamp,
                                values={"pm25": round(value + jitter, 3),
                                        "pm10": round((value + jitter) * 1.6, 3)},
                                sensor_id=f"fixture-line-{row}",
                                provenance=provenance,
                            )
                        )
        return out
