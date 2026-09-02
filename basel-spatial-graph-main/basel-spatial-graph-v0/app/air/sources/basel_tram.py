"""Particulate readings from sensors on BVB tram roofs (Open Data Basel-Stadt)."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..model import AirReading
from .base import LIVE, AirSource, make_air_provenance
from ...config import RAW_DIR
from ...ingest import cache_dataset_export, fetch_dataset_metadata

DATASET_ID = "100113"
DATASET_TITLE = "Feinstaubmessungen auf BVB-Trams"
DEFAULT_CACHE = RAW_DIR / "air" / f"{DATASET_ID}.csv"
BASEL_CET = timezone(timedelta(hours=1), name="CET")
MOBILE_SENSOR_EXCLUSIONS = {236, 240}

# Published deviation of this low-cost sensor class against reference
# instruments. Left as None until read off the comparison dataset — a made-up
# error band would be worse than an absent one, because the interface would
# render it as knowledge.
ERROR_BAND: Dict[str, Optional[float]] = {"pm25": None, "pm10": None}

# --- the seam -------------------------------------------------------------
# Each field lists the header names we are willing to accept, in order. The
# first one present in the file wins.
COLUMN_CANDIDATES = {
    "timestamp": ["time"],
    "sensor_id": ["sensornr"],
    "pm25": ["pm25"],
    "pm10": ["pm10"],
    "lon": ["longitude"],
    "lat": ["latitude"],
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
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp.astimezone(BASEL_CET)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).astimezone(BASEL_CET)
        except ValueError:
            continue
    return None


def _parse_row(row: dict, cols: Dict[str, Optional[str]], provenance: dict) -> Optional[AirReading]:
    lon = _to_float(row.get(cols["lon"])) if cols["lon"] else None
    lat = _to_float(row.get(cols["lat"])) if cols["lat"] else None
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
    sensor_id = row.get(cols["sensor_id"]) if cols["sensor_id"] else None
    try:
        sensor_number = int(sensor_id)
    except (TypeError, ValueError):
        return None
    if sensor_number in MOBILE_SENSOR_EXCLUSIONS:
        return None
    return AirReading(
        lon=lon, lat=lat, timestamp=stamp, values=values,
        sensor_id=str(sensor_number),
        provenance=provenance,
    )


class BaselTramAirSource(AirSource):
    mode = LIVE

    def __init__(self, path=None, retrieved_at: Optional[str] = None,
                 max_rows: Optional[int] = None, force_refresh: bool = False):
        """Use a local CSV/JSON file, or fetch and cache the official export."""
        self.path = Path(path) if path else DEFAULT_CACHE
        self.retrieved_at = retrieved_at
        self.max_rows = max_rows
        self.force_refresh = force_refresh
        self.skipped = 0
        self.metadata = None
        self.statistics = {}

    def error_band(self, pollutant: str) -> Optional[float]:
        return ERROR_BAND.get(pollutant)

    def readings(self) -> List[AirReading]:
        if not self.path.exists() or self.force_refresh:
            cache_dataset_export(
                DATASET_ID, self.path, force=self.force_refresh,
                where="sensornr != 236 AND sensornr != 240",
            )
        try:
            self.metadata = fetch_dataset_metadata(DATASET_ID)
        except Exception:
            self.metadata = None
        default_meta = (self.metadata or {}).get("metas", {}).get("default", {})
        dataset_id = (self.metadata or {}).get("dataset_id", DATASET_ID)
        provenance = make_air_provenance(
            mode=LIVE, source="Open Data Basel-Stadt", dataset=dataset_id,
            dataset_title=default_meta.get("title", DATASET_TITLE),
            source_url=f"https://data.bs.ch/explore/dataset/{dataset_id}/",
            license=default_meta.get("license"),
            retrieved_at=self.retrieved_at, sensor_class="low-cost mobile microsensor",
            source_last_update=default_meta.get("modified"),
        )
        out: List[AirReading] = []
        self.skipped = 0
        if self.path.suffix.lower() == ".json":
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            rows = payload.get("results", payload) if isinstance(payload, dict) else payload
            cols = _resolve(rows[0].keys() if rows else [])
            iterator = rows
        else:
            handle = self.path.open(newline="", encoding="utf-8-sig")
            sample = handle.read(8192)
            handle.seek(0)
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            cols = _resolve(reader.fieldnames or [])
            iterator = reader
        missing = [f for f in ("timestamp", "sensor_id", "lon", "lat") if not cols[f]]
        if missing:
            if self.path.suffix.lower() != ".json":
                handle.close()
            raise ValueError(f"{self.path.name}: missing confirmed columns: {', '.join(missing)}")
        try:
            for row in iterator:
                reading = _parse_row(row, cols, provenance)
                if reading is None:
                    self.skipped += 1
                    continue
                out.append(reading)
                if self.max_rows and len(out) >= self.max_rows:
                    break
        finally:
            if self.path.suffix.lower() != ".json":
                handle.close()
        months = Counter(r.timestamp.strftime("%Y-%m") for r in out)
        lockdown = datetime(2020, 3, 16, tzinfo=BASEL_CET)
        after_lockdown = sum(r.timestamp >= lockdown for r in out)
        self.statistics = {
            "readings_per_month": dict(sorted(months.items())),
            "readings_total": len(out),
            "readings_after_2020_03_16": after_lockdown,
            "fraction_after_2020_03_16": (
                after_lockdown / len(out) if out else 0.0
            ),
            "stationary_sensors_excluded": sorted(MOBILE_SENSOR_EXCLUSIONS),
        }
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
