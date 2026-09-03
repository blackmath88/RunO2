"""What is the low-cost sensor class actually worth, against reference instruments?

The air layer ships `ERROR_BAND = {"pm25": None, "pm10": None}` with a comment
saying a made-up band would be worse than an absent one. This script is the
attempt to replace that `None` with something earned.

Basel publishes a comparison campaign: three Sensirion "Nubo" microsensors were
installed at the Lufthygieneamt's permanent monitoring stations and run beside
the reference instruments.

    100178  Smarte Strasse: Luftqualitaet Vergleichsmessungen  (the microsensors)
    100050  Luftqualitaet Station Feldbergstrasse              (the reference)
    100049  Luftqualitaet Station St. Johannplatz              (the reference)

Pairing the two by hour gives a real bias and a real error for that sensor
class at those two sites.

The result does NOT transfer cleanly to the tram dataset, and the report says
so: different manufacturer, different years, different mounting. It bounds what
a well-run low-cost PM2.5 sensor achieves in Basel; it does not calibrate
sensors 227-237 retrospectively. Nobody ever ran that comparison.

    python experiments/sensor_calibration.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import fetch_dataset_metadata  # noqa: E402

import httpx  # noqa: E402

API = "https://data.bs.ch/api/explore/v2.1/catalog/datasets"
WINDOW = ("2022-02-01", "2023-07-01")

SITES = {
    "Feldbergstrasse": {"sensor_field": "feldbergstr2_pm25", "reference": "100050"},
    "St. Johannplatz": {"sensor_field": "stjohann2_pm25", "reference": "100049"},
}


def _rows(dataset: str, select: str, where: str | None = None) -> list[dict]:
    """Pull a filtered slice as CSV.

    The records endpoint refuses an offset past 10 000, and these comparisons
    need a year and a half of hourly values, so the export endpoint is the only
    one that can answer the question.
    """
    import csv
    import io

    params = {"select": select}
    if where:
        params["where"] = where
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(f"{API}/{dataset}/exports/csv", params=params)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig")
    delimiter = ";" if text.count(";") > text.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


def _hour(text: str) -> datetime | None:
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def compare(site: str, spec: dict) -> dict:
    field = spec["sensor_field"]
    sensor_rows = _rows(
        "100178", f"timestamp,{field}",
        f"timestamp >= date'{WINDOW[0]}' AND timestamp < date'{WINDOW[1]}' "
        f"AND {field} IS NOT NULL",
    )
    reference_rows = _rows(
        spec["reference"], "datum_zeit,pm2_5_stundenmittelwerte_ug_m3",
        f"datum_zeit >= date'{WINDOW[0]}' AND datum_zeit < date'{WINDOW[1]}' "
        f"AND pm2_5_stundenmittelwerte_ug_m3 IS NOT NULL",
    )
    sensor = {}
    for row in sensor_rows:
        hour = _hour(row.get("timestamp"))
        raw = row.get(field)
        if hour is not None and raw not in (None, ""):
            sensor.setdefault(hour, []).append(float(raw))
    reference = {}
    for row in reference_rows:
        hour = _hour(row.get("datum_zeit"))
        value = row.get("pm2_5_stundenmittelwerte_ug_m3")
        if hour is not None and value not in (None, ""):
            reference.setdefault(hour, []).append(float(value))

    pairs = [
        (float(np.mean(reference[h])), float(np.mean(sensor[h])))
        for h in sorted(set(sensor) & set(reference))
    ]
    if len(pairs) < 100:
        return {"site": site, "paired_hours": len(pairs),
                "conclusion": "too few paired hours to state anything"}

    ref = np.array([p[0] for p in pairs])
    sen = np.array([p[1] for p in pairs])
    diff = sen - ref
    slope, intercept = np.polyfit(ref, sen, 1)
    return {
        "site": site,
        "sensor_dataset": "100178",
        "reference_dataset": spec["reference"],
        "paired_hours": len(pairs),
        "window": {"from": str(min(set(sensor) & set(reference))),
                   "to": str(max(set(sensor) & set(reference)))},
        "reference_median_ug_m3": round(float(np.median(ref)), 2),
        "sensor_median_ug_m3": round(float(np.median(sen)), 2),
        "median_bias_ug_m3": round(float(np.median(diff)), 2),
        "mean_bias_ug_m3": round(float(np.mean(diff)), 2),
        "mean_absolute_error_ug_m3": round(float(np.mean(np.abs(diff))), 2),
        "rmse_ug_m3": round(float(np.sqrt(np.mean(diff ** 2))), 2),
        "p90_absolute_error_ug_m3": round(float(np.percentile(np.abs(diff), 90)), 2),
        "pearson_r": round(float(np.corrcoef(ref, sen)[0, 1]), 3),
        "regression": {"slope": round(float(slope), 3),
                       "intercept": round(float(intercept), 3)},
    }


def main() -> int:
    results = [compare(site, spec) for site, spec in SITES.items()]
    metadata = {ds: fetch_dataset_metadata(ds).get("metas", {}).get("default", {})
                for ds in ("100178", "100050", "100049")}
    payload = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_requested": WINDOW,
        "datasets": {ds: {"title": m.get("title"), "license": m.get("license"),
                          "records": m.get("records_count")}
                     for ds, m in metadata.items()},
        "sites": results,
    }
    print(json.dumps(payload, indent=2))
    out = Path(__file__).resolve().parent / "sensor_calibration.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwritten to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
