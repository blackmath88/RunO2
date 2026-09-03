# runO2

**Basel's trams measured the air. Can that data plan a run?**

A running-loop planner for Basel built on a typed spatial graph of the city —
and an honest answer to the question it was built to ask. Pick a start point, a
distance and an hour; compare a few candidate loops by air quality, coverage,
weather, pollen and terrain; export the one you want as GPX.

Built for the Hack am Rhein warm-up, on top of the
[Basel Spatial Graph](basel-spatial-graph-main/basel-spatial-graph-v0/README.md).

```bash
cd basel-spatial-graph-main/basel-spatial-graph-v0
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/run**.

The repository ships a frozen snapshot of real Basel data plus a 60 kB clip of
the federal air-quality rasters, so the planner works immediately with no
downloads. To add the measured tram layer:

```bash
python -m app.air.viability --csv data/raw/air/100113.csv \
  --out experiments/AIR_VIABILITY_REAL.md      # fetches 100113 on first run
```

---

## The finding

The project set out to rank running routes by what tram-mounted sensors
measured. It cannot be done with that data, and the reason took real numbers to
establish:

| Gate | Result | |
|---|---|---|
| **temporal** | rank disagreement **0.27** (needs ≥ 0.25) | passes — street rankings genuinely change by hour |
| **coverage** | **19.2%** of the 884 km walking network | thin — sensors ride on trams, so coverage follows the tram lines |
| **resolution** | signal ÷ noise **0.36** (needs ≥ 1.0) | **fails** |

The resolution gate is the one that decides it. Two streets in Basel differ by
**0.51 µg/m³** PM2.5 once city-wide weather is removed. Two sensors passing *the
same street in the same hour* differ by **1.41 µg/m³**. The instruments disagree
with each other nearly three times as much as the streets differ from each
other, so ranking routes by these values ranks noise.

More trams would add coverage, not resolution. Only calibration would — and
Basel's own sensor-comparison campaign says why: this class of microsensor
under-reports PM2.5 by 3–4.6 µg/m³ against reference instruments, with a typical
hourly error of ~5 µg/m³. That is roughly ten times the signal the product would
need to see.

The dataset is also closed. The campaign ran December 2019 to March 2020; the
publisher states no further data will be added, and set the update interval to
`NEVER` in 2023.

## What runO2 does instead

Four open layers, each doing only what it can, which is what the planner now
runs on:

| Layer | Source | Contributes |
|---|---|---|
| **spatial baseline** | federal NO₂ model, 20 m raster, annual | which streets are structurally worse — **99.5%** of the network, **3.0 µg/m³** between two streets |
| **current level** | LHA reference stations, hourly, live | what the air is actually doing right now |
| **forecast** | Open-Meteo / CAMS | temperature, rain, wind, AQI, pollen for the hour you will run |
| **uncertainty** | comparison campaign `100178` | what a low-cost reading is worth |
| *(corroboration)* | tram sensors, where they passed | shown beside the ranking, never setting it |

Six times the street contrast of the tram data, over five times as much of the
network, and current. The full comparison, with method and licences, is in
**[docs/DATA_FIT.md](basel-spatial-graph-main/basel-spatial-graph-v0/docs/DATA_FIT.md)**.

## Provenance

Every value on screen carries its class, and the four are never blended:

| Class | Meaning |
|---|---|
| `measured` | a sensor read this street. Carries dataset, window and reading count. |
| `modelled` | a national model's annual mean. Not a measurement, not valid for one address. |
| `forecast` | a model's expectation for an hour that has not happened yet. |
| `dynamic` | computed for this request, from these parameters. |
| `unmeasured` | nobody has ever measured here. **Unknown, not clean.** |

`unmeasured` is the load-bearing one and most of the test suite defends it: an
unmeasured segment never acquires a value, contributes nothing to a total,
cannot rank as cleanest by being unknown, and travels with its share into the
GPX file. An interpolated surface would have been easier and would have quietly
turned ignorance into a recommendation.

runO2 compares route candidates. It does not estimate personal exposure and
makes no health claim.

## Layout

```
docs/                              concept, UX direction, weather reference
basel-spatial-graph-main/
  basel-spatial-graph-v0/          the application
    app/air/                       the run planner
      noise.py                     the resolution gate
      baseline.py                  federal modelled rasters
      conditions.py                weather, pollen, terrain
    docs/DATA_FIT.md               which data can carry the product
    experiments/                   viability and calibration evidence
```

## Documentation

- [DATA_FIT.md](basel-spatial-graph-main/basel-spatial-graph-v0/docs/DATA_FIT.md) — which open datasets can carry runO2, and why
- [CLEAN_AIR_RUN.md](basel-spatial-graph-main/basel-spatial-graph-v0/docs/CLEAN_AIR_RUN.md) — the air layer's design
- [AIR_VIABILITY_REAL.md](basel-spatial-graph-main/basel-spatial-graph-v0/experiments/AIR_VIABILITY_REAL.md) — the gates, on real data
- [Basel Spatial Graph](basel-spatial-graph-main/basel-spatial-graph-v0/README.md) — the graph underneath
- [ATTRIBUTION.md](ATTRIBUTION.md) — data sources and licences

---

Code: MIT ([LICENSE](LICENSE)). Committed data keep their upstream licences —
Open Data Basel-Stadt (CC BY 4.0), © Data BAFU / swisstopo, Open-Meteo
(CC BY 4.0), OpenStreetMap contributors (ODbL 1.0), opentransportdata.swiss.
