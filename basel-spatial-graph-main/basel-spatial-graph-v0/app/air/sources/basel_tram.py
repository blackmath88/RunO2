"""Particulate readings from sensors on BVB tram roofs (Open Data Basel-Stadt).

    !!  THE SCHEMA HERE IS UNVERIFIED.  !!

This adapter was written without network access to data.bs.ch, so the column
names below are an assumption, not an observation. Everything else in this
package is tested against the fixture source and does not depend on them.

When the real export is in hand, the only thing that should need changing is
`COLUMN_CANDIDATES` and, if the file is stranger than expected, `_parse_row`.
That is the whole point of keeping the seam this narrow: one dict and one
function stand between an assumption and a working pipeline.

Run `python -m app.air.sources.basel_tram --inspect <file.csv>` to print the
real header and the first parsed rows before trusting anything downstream.
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..model import AirReading
from .base import LIVE, AirSource, make_air_provenance

DATASET_ID = "100081"          # placeholder until confirmed against the portal
DATASET_TITLE = "Particulate readings from the roofs of BVB trams"
SOURCE_URL = "https://data.bs.ch/explore/dataset/100081/"
LICENSE = "CC BY 4.0"

# Published deviation of this low-cost sensor class against reference
# instruments. Left as None until read off the comparison dataset — a made-up
# error band would be worse than an absent one, because the interface would
# render it as knowledge.
ERROR_BAND: Dict[str, Optional[float]] = {"pm25": None, "pm10": None}

# --- the seam -------------------------------------------------------------
# Each field lists the header names we are willing to accept, in order. The
# first one present in the file wins.
COLUMN_CANDIDATES = {
    "lon": ["lon", "longitude", "laenge", "x", "geo_point_2d_lon"],
    "lat": ["lat", "latitude", "breite", "y", "geo_point_2d_lat"],
    "geopoint": ["geo_point_2d", "geopunkt", "coordinates"],
    "timestamp": ["timestamp", "zeitstempel", "datum_zeit", "date_time", "time"],
    "pm25": ["pm2_5", "pm25", "pm2.5", "feinstaub_pm2_5"],
    "pm10": ["pm10", "pm_10", "feinstaub_pm10"],
    "sensor_id": ["sensor_id", "sensor", "fahrzeug", "vehicle_id", "device"],
}
# --------------------------------------------------------------------------


def _resolve(header: Iterable[str]) -> Dict[str, Optional[str]]:
    lowered = {h.strip().lower(): h for h in header}
    resolved = {}
    for field, candidates in COLUMN_CANDIDATES.items():
        resolved[field] = next((lowered[c] for c in candidates if c in lowered), None)
    return resolved


def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _parse_timestamp(value) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parse in (datetime.fromisoformat,):
        try:
            stamp = parse(text)
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_row(row: dict, cols: Dict[str, Optional[str]], provenance: dict) -> Optional[AirReading]:
    lon = _to_float(row.get(cols["lon"])) if cols["lon"] else None
    lat = _to_float(row.get(cols["lat"])) if cols["lat"] else None
    if (lon is None or lat is None) and cols["geopoint"]:
        raw = str(row.get(cols["geopoint"]) or "")
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) == 2:                      # Opendatasoft writes "lat, lon"
            lat, lon = _to_float(parts[0]), _to_float(parts[1])
    stamp = _parse_timestamp(row.get(cols["timestamp"])) if cols["timestamp"] else None
    if lon is None or lat is None or stamp is None:
        return None
    values = {}
    for pollutant in ("pm25", "pm10"):
        column = cols.get(pollutant)
        value = _to_float(row.get(column)) if column else None
        if value is not None and value >= 0:
            values[pollutant] = value
    if not values:
        return None
    return AirReading(
        lon=lon, lat=lat, timestamp=stamp, values=values,
        sensor_id=row.get(cols["sensor_id"]) if cols["sensor_id"] else None,
        provenance=provenance,
    )


class BaselTramAirSource(AirSource):
    mode = LIVE

    def __init__(self, path, retrieved_at: Optional[str] = None, max_rows: Optional[int] = None):
        self.path = Path(path)
        self.retrieved_at = retrieved_at
        self.max_rows = max_rows
        self.skipped = 0

    def error_band(self, pollutant: str) -> Optional[float]:
        return ERROR_BAND.get(pollutant)

    def readings(self) -> List[AirReading]:
        provenance = make_air_provenance(
            mode=LIVE, source="Open Data Basel-Stadt", dataset=DATASET_ID,
            dataset_title=DATASET_TITLE, source_url=SOURCE_URL, license=LICENSE,
            retrieved_at=self.retrieved_at, sensor_class="low-cost mobile microsensor",
        )
        out: List[AirReading] = []
        self.skipped = 0
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            sample = handle.read(8192)
            handle.seek(0)
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            cols = _resolve(reader.fieldnames or [])
            missing = [f for f in ("timestamp",) if not cols[f]]
            if missing or not (cols["lon"] or cols["geopoint"]):
                raise ValueError(
                    f"{self.path.name}: could not find the expected columns. "
                    f"Header was {reader.fieldnames}. Fix COLUMN_CANDIDATES in "
                    f"{__name__} rather than guessing downstream."
                )
            for row in reader:
                reading = _parse_row(row, cols, provenance)
                if reading is None:
                    self.skipped += 1
                    continue
                out.append(reading)
                if self.max_rows and len(out) >= self.max_rows:
                    break
        return out


def _inspect(path: str, rows: int = 5) -> None:
    """Print the real header and a few parsed rows. Run this first."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        print("delimiter:", repr(delimiter))
        print("header:", reader.fieldnames)
        print("resolved:", _resolve(reader.fieldnames or []))
        for i, row in enumerate(reader):
            if i >= rows:
                break
            print(row)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--inspect":
        _inspect(sys.argv[2])
    else:
        print(__doc__)
