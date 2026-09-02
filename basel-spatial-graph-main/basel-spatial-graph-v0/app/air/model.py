"""What an air reading is, and how honest we are about each one.

The graph already classifies values as observed / official / derived / dynamic.
Mobile sensor data forces one addition that the rest of the project never
needed:

    measured     a tram carrying a sensor passed this street and read a value
    unmeasured   no tram ever passed here, so nothing is known

`unmeasured` is the point. A street with no reading is not a clean street, and
an interpolated surface would quietly turn ignorance into a recommendation.
Every downstream computation carries the unmeasured share with it, and the
interface renders it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

MEASURED = "measured"
UNMEASURED = "unmeasured"

AIR_CLASSIFICATIONS = {
    MEASURED: "Read by a mobile sensor that passed this location.",
    UNMEASURED: "No sensor has ever passed here. The value is unknown, not zero.",
}

# Pollutants we accept. PM2.5 is the one that matters for exercise; PM10 comes
# in the same feed and is kept because dropping a column you were given is a
# decision you cannot reverse later.
POLLUTANTS = ("pm25", "pm10")


@dataclass(frozen=True)
class AirReading:
    """One sensor reading at one place and time."""

    lon: float
    lat: float
    timestamp: datetime
    values: Dict[str, float]          # pollutant -> concentration, ug/m3
    sensor_id: Optional[str] = None
    provenance: dict = field(default_factory=dict)

    @property
    def hour(self) -> int:
        return self.timestamp.hour


@dataclass
class SegmentAir:
    """What is known about the air on one street segment.

    `by_hour` holds the same statistic split by hour of day, and `by_hour_p90`
    the spread within each hour — needed because diurnal variation would
    otherwise be mistaken for sensor noise when judging whether streets
    really differ from one another. It stays empty
    when the viability check says the temporal signal is not there, and the
    interface drops the hour strip accordingly rather than showing noise.
    """

    segment_id: str
    pollutant: str
    median: Optional[float] = None
    p90: Optional[float] = None
    reading_count: int = 0
    by_hour: Dict[int, float] = field(default_factory=dict)
    by_hour_p90: Dict[int, float] = field(default_factory=dict)
    error_band: Optional[float] = None   # from the reference-comparison dataset
    provenance: dict = field(default_factory=dict)

    @property
    def classification(self) -> str:
        return MEASURED if self.reading_count > 0 else UNMEASURED

    @property
    def known(self) -> bool:
        return self.median is not None

    def value_at_hour(self, hour: Optional[int]) -> Optional[float]:
        if hour is None or not self.by_hour:
            return self.median
        return self.by_hour.get(int(hour), self.median)

    def as_provenance(self) -> dict:
        """The record the interface shows when someone taps this segment."""
        base = {
            "segment_id": self.segment_id,
            "classification": self.classification,
            "explanation": AIR_CLASSIFICATIONS[self.classification],
            "pollutant": self.pollutant,
            "reading_count": self.reading_count,
        }
        if self.known:
            base["median"] = round(self.median, 2)
            base["p90"] = round(self.p90, 2) if self.p90 is not None else None
            base["unit"] = "ug/m3"
            if self.error_band is not None:
                base["error_band"] = round(self.error_band, 2)
                base["error_band_note"] = (
                    "Low-cost sensor deviation against reference instruments, "
                    "from the published comparison measurements."
                )
        base.update({k: v for k, v in (self.provenance or {}).items()})
        return base


@dataclass
class Coverage:
    """How much of the network anyone actually knows anything about."""

    segments_total: int
    segments_measured: int
    network_length_m: float
    measured_length_m: float

    @property
    def segment_share(self) -> float:
        return self.segments_measured / self.segments_total if self.segments_total else 0.0

    @property
    def length_share(self) -> float:
        return self.measured_length_m / self.network_length_m if self.network_length_m else 0.0

    def as_dict(self) -> dict:
        return {
            "segments_total": self.segments_total,
            "segments_measured": self.segments_measured,
            "segments_unmeasured": self.segments_total - self.segments_measured,
            "segment_share": round(self.segment_share, 4),
            "length_share": round(self.length_share, 4),
            "network_length_km": round(self.network_length_m / 1000.0, 2),
            "note": (
                "Sensors ride on trams, so coverage follows the tram network. "
                "Unmeasured streets are shown as unmeasured, never as clean."
            ),
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
