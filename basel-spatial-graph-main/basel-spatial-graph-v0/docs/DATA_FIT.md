# Which open data can actually carry runO2?

runO2 asks a narrow question: **can Basel's open air-quality data rank a few
running loops against each other?**

Not "is the air good", not "what will I inhale" — can two routes be told apart.
That is a much lower bar than a health claim and a much higher one than a map.
This document reports what each candidate dataset can and cannot do against
that bar, using one statistic throughout so the sources are comparable.

## The measuring stick

> **Street contrast** — the median difference between two randomly chosen
> streets in Basel's 884 km walking network.
>
> **Noise floor** — the median disagreement between two independent
> observations of *the same street*.

A dataset can rank routes when street contrast comfortably exceeds its noise
floor. Everything below is that one comparison, applied to each source.

Reproduce: `python -m app.air.viability --csv data/raw/air/100113.csv`,
`python experiments/sensor_calibration.py`, `python -m app.air.baseline --prepare`.

---

## The comparison

| Dataset | Measured / modelled | Spatial coverage | Temporal resolution | Street contrast | Good for | Weakness | runO2 role |
|---|---|---|---|---|---|---|---|
| **BVB tram sensors** (`100113`) | measured, low-cost mobile | 19.2% of network length, tram corridors only | ~1 min while running, **campaign closed Mar 2020** | **0.51 µg/m³** PM2.5 | proving mobile monitoring is possible; showing where trams go | noise floor 1.41 µg/m³ — 2.8× the contrast; six years stale; never updated again | the experiment, and the evidence for why it is not the product |
| **Fixed microsensors** (`100081`, `100093`, `100275`) | measured, low-cost fixed | ~10 points citywide | continuous | n/a — point data | continuity, local context, validation | far too few points to route on | context, not routing |
| **Reference stations** (`100049`, `100050`, `100048`, `100051`) | measured, reference-grade | 4 points | hourly, **live, updated today** | n/a — point data | the true current level; calibration ground truth | 4 locations for a 884 km network | the "what is the air doing right now" layer |
| **Sensor comparison** (`100178`) | measured, sensor vs reference | 3 co-located sites | hourly, 2022‑02 → 2023‑06 | n/a — a calibration study | the only real error figure for this sensor class in Basel | different sensor model and years than the trams | the uncertainty statement |
| **Federal PM2.5 model** (`ch.bafu.luftreinhaltung-feinstaub_pm2_5`) | **modelled** | **99.2%** of network, 100 m raster | annual mean, since 2015 | **1.00 µg/m³** | regional background | PM2.5 is largely regional — it barely varies within one city | weak baseline |
| **Federal NO₂ model** (`ch.bafu.luftreinhaltung-stickstoffdioxid`) | **modelled** | **99.5%** of network, **20 m raster** | annual mean, since 2020 at 20 m | **3.00 µg/m³** | traffic-related exposure at street scale | annual mean — no hour, no weather; pixels not valid for single addresses | **the spatial baseline runO2 ranks on** |
| **Open-Meteo forecast + CAMS** | forecast | regional | hourly | n/a — one value for the city | temperature, rain, wind, AQI, pollen | cannot separate two streets in one city | the conditions layer |

---

## A. BVB tram data (`100113`) — the experiment

**Role:** mobile observation; high temporal detail; sparse corridor coverage.

**What it does deliver.** 613,723 usable readings from five sensors on tram
roofs. Real observations at street level, at roughly one-minute cadence, across
a fifth of Basel's walking network. Segment rankings genuinely change between
morning and evening (rank disagreement 0.273) — the hour-of-day control is
justified by the data.

**Why it cannot rank routes.** Three numbers, from
`experiments/AIR_VIABILITY_REAL.md`:

| | µg/m³ PM2.5 |
|---|---|
| Difference between two streets, once city-wide weather is removed | **0.51** |
| Disagreement between two sensors on the same street in the same hour | **1.41** |
| Signal-to-noise ratio | **0.36** |

The instruments disagree with each other nearly three times as much as the
streets differ from each other. Individual sensor pairs carry systematic offsets
up to 4.2 µg/m³, and per-sensor campaign medians span 6.04 to 12.30 µg/m³ — a
two-fold range between instruments that all rode the same city.

This is not a coverage problem. **More trams would add coverage, not
resolution.** Only calibration would.

**And it is closed.** The publisher's own metadata: the campaign ran December
2019 to March 2020, *"no further measurement data will be added and the dataset
is no longer updated"*; the update interval was set to `NEVER` in 2023. 96% of
readings predate 16 March 2020. Whatever this data supports, it cannot be
"what is the air on my run this evening".

## B. Sensor comparison (`100178`) — what the class is worth

**Question asked:** can this dataset put a defensible error band on low-cost
PM2.5 sensors, so the interface can render uncertainty instead of implying
precision?

**Method.** `100178` publishes hourly PM2.5 from three Sensirion "Nubo"
microsensors installed at the Lufthygieneamt's permanent stations. It does *not*
contain the reference values — those live in the station datasets. Pairing them
by hour gives a real comparison. See `experiments/sensor_calibration.py`.

| Site | Paired hours | Reference median | Sensor median | Median bias | MAE | RMSE | Pearson r | Slope |
|---|---|---|---|---|---|---|---|---|
| Feldbergstrasse (`100050`) | 8,393 | 12.42 | 6.35 | **−4.62** | **5.85** | 6.90 | 0.860 | 1.16 |
| St. Johannplatz (`100049`) | 9,680 | 9.72 | 5.20 | **−3.07** | **4.65** | 5.79 | 0.898 | 1.41 |

**What can be concluded.** These microsensors **under-report PM2.5 by roughly 3
to 4.6 µg/m³ at the median** — a 32–37% underestimate against reference
instruments — while tracking changes well (r ≈ 0.86–0.90). Slopes above 1 with
large negative intercepts mean the under-reporting is worst at low
concentrations. Typical absolute error for one hourly value is **4.7–5.9
µg/m³**.

Set that beside the tram street contrast of **0.51 µg/m³**: the error of a
well-sited example of this sensor class is about ten times the spatial signal
runO2 would need to detect. Two independent lines of evidence, one internal to
the tram data and one external, agree.

**What cannot be concluded, and is therefore not claimed.** This is a different
sensor model (Sensirion Nubo, 2022–23) from the tram sensors (Atmo-VISION,
2019–20), differently mounted, in different years. It **bounds what this class
of instrument achieves in Basel; it does not calibrate sensors 227–237.** That
comparison was never run, and no arithmetic here can invent it.

Accordingly `ERROR_BAND` in `app/air/sources/basel_tram.py` stays `None`.
Transferring a measured figure across sensor models would render a guess as
knowledge, which is the specific failure this project exists to avoid.

## C. Federal modelled air quality — the layer that works

Published by the Bundesamt für Umwelt via swisstopo as Cloud-Optimized GeoTIFF
in **EPSG:2056** — the metric CRS this project already projects into.

| | PM2.5 | NO₂ |
|---|---|---|
| Collection | `ch.bafu.luftreinhaltung-feinstaub_pm2_5` | `ch.bafu.luftreinhaltung-stickstoffdioxid` |
| Spatial resolution | 100 m | **20 m** (since 2020; 200 m before) |
| Temporal resolution | annual mean, since 2015 | annual mean, since 1990 |
| Newest year | 2025 | 2025 |
| Coverage of Basel's walking network | 99.2% | **99.5%** |
| Range across the network | 8–13 µg/m³ | **8–48 µg/m³** (middle 80%: 11–20) |
| Street contrast | 1.00 µg/m³ | **3.00 µg/m³** |
| LRV annual limit | 10 µg/m³ | 30 µg/m³ |
| Licence | free use with source citation | free use with source citation |

**Feasibility of sampling along a route: trivial.** Clipping both rasters to
Basel produces a **60 kB** file (`data/processed/basel_air_baseline.npz`);
sampling every one of 19,258 segment midpoints is an array lookup. The whole
pipeline is `app/air/baseline.py`, and the server never touches the network —
the same promise the rest of this repository makes.

**Why NO₂ rather than PM2.5.** PM2.5 in Switzerland is largely regional and
secondary; it does not vary much between two streets in one city, and the
raster confirms it (1.00 µg/m³ contrast, most of Basel pinned at the 10 µg/m³
limit value). NO₂ is dominated by local traffic — which is precisely the thing a
runner choosing between a quay and an arterial is choosing between. Three times
the contrast, five times the resolution.

**The honest limits, stated wherever it is rendered.** It is *modelled*, not
measured. It is an *annual mean* — no hour, no weather, no today. And BAFU
states plainly that individual pixels must not be used to assess individual
locations. runO2 uses it the one way that survives all three caveats: as a
**relative comparison between route candidates**, never as a statement about an
address.

---

## What would actually make runO2 work

No single dataset does it. Four layers, each doing only what it can:

| Layer | Source | What it contributes | What it must not claim |
|---|---|---|---|
| **Spatial baseline** | Federal NO₂ 20 m raster | which streets are structurally worse, everywhere | not today, not this hour, not an address |
| **Current level** | Reference stations `100049`/`100050`, hourly and live | what the air is doing right now, accurately | one number for the whole city |
| **Forecast** | Open-Meteo / CAMS | conditions for the hour someone will actually run | regional, cannot separate streets |
| **Uncertainty** | Comparison study `100178` | what a low-cost reading is worth | does not transfer between sensor models |
| *(local measurement)* | tram / microsensors, where present | corroboration and provenance | cannot set the ranking |

Multiply the spatial pattern by the current level, state the uncertainty, and
show coverage. That combination is buildable **today**, entirely from open data,
and it is what runO2 now ranks on.

The dataset that inspired the project turns out to be the one layer that cannot
carry it. That is the finding, and it took real data to reach it.

---

*Data: Open Data Basel-Stadt (CC BY 4.0) · © Data: BAFU / swisstopo · Open-Meteo
(CC BY 4.0) · OpenStreetMap contributors (ODbL 1.0)*
