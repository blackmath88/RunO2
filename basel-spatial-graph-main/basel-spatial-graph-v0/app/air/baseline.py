"""The federal modelled baseline: what is known about air *everywhere* in Basel.

The tram data answers "what did a sensor read on this street", for the fifth of
the network a tram ever crossed, in one winter six years ago. This module
answers a different question — "what does the national model say this street is
like in an average year" — for effectively the whole network.

    ch.bafu.luftreinhaltung-stickstoffdioxid    NO2, 20 m raster, annual mean
    ch.bafu.luftreinhaltung-feinstaub_pm2_5     PM2.5, 100 m raster, annual mean

Both are published by the Bundesamt fuer Umwelt as Cloud-Optimized GeoTIFF in
EPSG:2056 — the metric CRS this project already projects into — so sampling a
route is a coordinate lookup and nothing more.

Two things this layer is not, and the interface must not imply otherwise:

  * It is **modelled**, not measured. A new provenance class says so.
  * It is an **annual mean**. It carries no hour, no day and no weather. BAFU
    states plainly that individual pixels are not to be used to assess
    individual locations, so this is a relative comparison between route
    options — never a statement about one address.

NO2 rather than PM2.5 is the useful one for route choice, and the numbers say
why: across Basel's walking network the NO2 raster puts two random streets
3.0 ug/m3 apart, the PM2.5 raster 1.0. PM2.5 in Switzerland is largely regional
and secondary — it does not vary much between two streets in one city. NO2 is
dominated by local traffic, which is exactly the thing a runner is choosing
between.

Preparation (once, writes a small clipped array into data/processed):

    python -m app.air.baseline --prepare
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..config import PROCESSED_DIR
from .model import utc_now_iso

MODELLED = "modelled"

COLLECTIONS = {
    "no2": {
        "collection": "ch.bafu.luftreinhaltung-stickstoffdioxid",
        "title": "Luftbelastung durch Stickstoffdioxid",
        "resolution_m": 20,
        "limit_ug_m3": 30.0,       # LRV annual limit
        "unit": "ug/m3",
    },
    "pm25": {
        "collection": "ch.bafu.luftreinhaltung-feinstaub_pm2_5",
        "title": "Luftbelastung durch Feinstaub PM2.5",
        "resolution_m": 100,
        "limit_ug_m3": 10.0,
        "unit": "ug/m3",
    },
}
STAC = "https://data.geo.admin.ch/api/stac/v1/collections"
BASELINE_CACHE = PROCESSED_DIR / "basel_air_baseline.npz"
ATTRIBUTION = "© Data: BAFU / swisstopo"
LICENSE = "Free use with source citation (geo.admin.ch terms of use)"
BASEL_BOUNDS_2056 = (2603000.0, 1262000.0, 2620000.0, 1275000.0)


@dataclass
class BaselineSample:
    """One pollutant's modelled value at one place."""

    pollutant: str
    value: Optional[float]
    year: Optional[int]
    resolution_m: Optional[int]

    @property
    def known(self) -> bool:
        return self.value is not None


class AirBaseline:
    """Clipped federal rasters over Basel, sampled by metric coordinate."""

    def __init__(self, path: Path = BASELINE_CACHE):
        self.path = Path(path)
        data = np.load(self.path, allow_pickle=False)
        self.grids: Dict[str, np.ndarray] = {}
        self.meta: Dict[str, dict] = {}
        for pollutant in COLLECTIONS:
            key = f"{pollutant}_grid"
            if key not in data:
                continue
            self.grids[pollutant] = data[key]
            self.meta[pollutant] = {
                "year": int(data[f"{pollutant}_year"]),
                "resolution_m": int(data[f"{pollutant}_res"]),
                "transform": tuple(float(v) for v in data[f"{pollutant}_transform"]),
            }

    @classmethod
    def available(cls, path: Path = BASELINE_CACHE) -> bool:
        return Path(path).exists()

    def sample(self, xs: Sequence[float], ys: Sequence[float],
               pollutant: str = "no2") -> List[Optional[float]]:
        """Values at metric (EPSG:2056) coordinates. `None` outside the clip."""
        grid = self.grids.get(pollutant)
        if grid is None:
            return [None] * len(xs)
        meta = self.meta[pollutant]
        a, b, c, d, e, f = meta["transform"]        # affine: x = a*col + b*row + c
        xs_a, ys_a = np.asarray(xs, float), np.asarray(ys, float)
        # Inverse of the affine transform; b and d are zero for a north-up raster.
        cols = np.round((xs_a - c) / a).astype(int)
        rows = np.round((ys_a - f) / e).astype(int)
        inside = (rows >= 0) & (rows < grid.shape[0]) & (cols >= 0) & (cols < grid.shape[1])
        out: List[Optional[float]] = [None] * len(xs_a)
        values = grid[rows[inside], cols[inside]]
        for slot, value in zip(np.flatnonzero(inside), values):
            out[int(slot)] = None if np.isnan(value) else float(value)
        return out

    def provenance(self, pollutant: str = "no2") -> dict:
        spec = COLLECTIONS[pollutant]
        meta = self.meta.get(pollutant, {})
        return {
            "classification": MODELLED,
            "explanation": (
                "Modelled annual mean from the federal air-quality maps. Not a "
                "measurement, and not valid for a single address — BAFU states "
                "that individual pixels must not be used to assess individual "
                "locations. Used here to compare route options with each other."
            ),
            "source": "Bundesamt fuer Umwelt (BAFU) via swisstopo",
            "dataset": spec["collection"],
            "dataset_title": spec["title"],
            "source_url": f"https://data.geo.admin.ch/browser/index.html#/collections/{spec['collection']}",
            "license": LICENSE,
            "attribution": ATTRIBUTION,
            "year": meta.get("year"),
            "resolution_m": meta.get("resolution_m"),
            "temporal_resolution": "annual mean",
            "limit_value_ug_m3": spec["limit_ug_m3"],
            "unit": spec["unit"],
        }


def prepare(bounds: Tuple[float, float, float, float] = BASEL_BOUNDS_2056,
            path: Path = BASELINE_CACHE) -> Path:
    """Clip the newest federal rasters to Basel and store them locally.

    A national 20 m raster is 18000x12000; Basel is a 850x650 corner of it. The
    clip is small enough to commit, which keeps the promise the rest of this
    repository makes: the server reads prepared data and never downloads.
    """
    import httpx
    import rasterio
    from rasterio.windows import from_bounds

    payload: Dict[str, np.ndarray] = {}
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for pollutant, spec in COLLECTIONS.items():
            items = client.get(
                f"{STAC}/{spec['collection']}/items", params={"limit": 100}
            ).json()["features"]
            items.sort(key=lambda i: i["properties"]["datetime"])
            newest = items[-1]
            year = int(newest["properties"]["datetime"][:4])
            href = next(a["href"] for name, a in newest["assets"].items()
                        if name.endswith("_2056.tif"))
            with rasterio.open(f"/vsicurl/{href}") as src:
                window = from_bounds(*bounds, transform=src.transform)
                grid = src.read(1, window=window).astype("float32")
                transform = src.window_transform(window)
                if src.nodata is not None:
                    grid[grid == src.nodata] = np.nan
            payload[f"{pollutant}_grid"] = grid
            payload[f"{pollutant}_year"] = np.array(year)
            payload[f"{pollutant}_res"] = np.array(spec["resolution_m"])
            payload[f"{pollutant}_transform"] = np.array(
                [transform.a, transform.b, transform.c,
                 transform.d, transform.e, transform.f], dtype="float64"
            )
            print(f"{pollutant}: {year}, {grid.shape[1]}x{grid.shape[0]} "
                  f"at {spec['resolution_m']} m")
    payload["prepared_at"] = np.array(utc_now_iso())
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    print(f"written to {path} ({path.stat().st_size/1024:.0f} kB)")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true",
                        help="download and clip the federal rasters over Basel")
    args = parser.parse_args(argv)
    if args.prepare:
        prepare()
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
