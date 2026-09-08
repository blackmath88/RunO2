# runO2

**Basel's trams measured the air. Can that data plan a run?**

runO2 is a quick **Hack am Rhein Warm Up 2026** experiment: a running-loop planner for Basel built on a typed spatial graph of the city — and an honest answer to the question it was built to ask.

**Live app:** https://runo2.bridge-work.ai  
**Hack am Rhein Warm Up:** https://hackamrhein.dev/warm-up

Pick a start point, distance and hour; compare a few candidate loops by air-quality evidence, coverage, weather, pollen and terrain; export the one you want as GPX.

> A route planner? Maybe. An experiment in what open data can actually tell us? Definitely.

## Why this exists

The Warm Up highlighted a wonderfully specific Basel dataset: particulate-matter measurements collected by sensors mounted on trams.

The first idea was obvious:

```text
tram measurements
      +
walking network
      ↓
compare running routes
      ↓
pick the cleaner route
```

But before turning the readings into a recommendation, the project tested whether the measurements could actually distinguish one street from another.

They could not.

## The finding

| Gate | Result | |
|---|---|---|
| **temporal** | rank disagreement **0.27** (needs ≥ 0.25) | passes — street rankings genuinely change by hour |
| **coverage** | **19.2%** of the 884 km walking network | thin — sensors ride on trams, so coverage follows the tram lines |
| **resolution** | signal ÷ noise **0.36** (needs ≥ 1.0) | **fails** |

Two streets in Basel differ by **0.51 µg/m³ PM2.5** once city-wide weather is removed. Two sensors passing the **same street in the same hour** differ by **1.41 µg/m³**.

The instruments disagree with each other nearly three times as much as the streets differ from each other. Ranking routes by those values would rank noise.

More trams would improve coverage, not resolution.

That failed first hypothesis became the interesting part of the project.

## Why the data stack widened

No single source can carry the whole product question, so runO2 keeps several evidence layers separate:

| Layer | Source | Contributes |
|---|---|---|
| **spatial baseline** | federal NO₂ model, 20 m raster, annual | which streets are structurally worse — **99.5%** of the network, **3.0 µg/m³** between two streets |
| **current level** | LHA reference stations, hourly, live | what the air is actually doing right now |
| **forecast** | Open-Meteo / CAMS | temperature, rain, wind, AQI, pollen for the hour you will run |
| **uncertainty** | comparison campaign `100178` | what a low-cost reading is worth |
| **corroboration** | tram sensors, where they passed | historical local evidence, shown beside the ranking but never setting it |
| **route substrate** | OpenStreetMap / Basel Spatial Graph | candidate loop generation and deterministic routing |

The full comparison, method and licences are in **[DATA_FIT.md](basel-spatial-graph-main/basel-spatial-graph-v0/docs/DATA_FIT.md)**.

## Provenance before cleverness

Every value on screen carries its evidence class and the classes are never blended:

| Class | Meaning |
|---|---|
| `measured` | a sensor read this street; carries dataset, window and reading count |
| `modelled` | a national model's annual mean; not a street measurement |
| `forecast` | a model's expectation for an hour that has not happened yet |
| `dynamic` | computed for this request, from these parameters |
| `unmeasured` | nobody measured here — **unknown, not clean** |

The runtime now fails closed if the valid federal NO₂ baseline is unavailable: it will not silently fall back to tram PM2.5 for ranking after the project has already established that the tram signal cannot support that claim.

runO2 compares route candidates. It does **not** estimate personal exposure and makes **no health claim**.

## Is this a product?

Maybe — but that is deliberately still an open question.

This was a quick hackathon build, not a validated health or consumer product. Open questions include:

- Is the available evidence strong enough to influence a route meaningfully?
- Do runners care enough about the difference to change where they run?
- Does combining multiple bounded sources improve the decision, or just make it look more sophisticated?
- Would the idea work substantially better in a city with denser, calibrated and current mobile sensing?

What seems more durable than the route-planner idea is the architectural question underneath it:

> Can applications distinguish between data that is available, evidence that is usable, and conclusions that are unsupported?

## Built heavily with AI

This project was built with extensive use of **ChatGPT, Claude, delta.dev and VS Code** for research, coding, refactoring, testing, architecture review, UX iteration and documentation.

The intended boundary is simple:

> AI can propose code and interpretations. It does not decide what the data is allowed to prove.

The evidence checks, provenance classes and deterministic route logic remain explicit and reproducible.

## Run locally

```bash
cd basel-spatial-graph-main/basel-spatial-graph-v0
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/run**.

The repository ships a frozen snapshot of real Basel data plus a small clip of the federal air-quality raster, so the planner works immediately without rebuilding the data pipeline.

## Cloudflare deployment

Production is designed for **Cloudflare Worker + Cloudflare Container** at:

```text
https://runo2.bridge-work.ai
```

The Worker is the public/custom-domain entry point. The existing FastAPI app runs unchanged inside a Linux container, which is a better fit for its `networkx`, `numpy`, `shapely` and `pyproj` runtime dependencies than rewriting the project for a WASM-specific environment.

Deployment files:

```text
Dockerfile
cloudflare/worker.ts
wrangler.jsonc
.github/workflows/deploy-cloudflare.yml
```

GitHub Actions expects repository secrets:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

Once configured, pushes affecting the app/deployment files deploy via Wrangler. The custom domain is declared in `wrangler.jsonc`; Cloudflare creates the DNS record and certificate when the deployment is authorized.

## Layout

```text
docs/                              concept and UX material
cloudflare/                         Worker front door
basel-spatial-graph-main/
  basel-spatial-graph-v0/          FastAPI application + prepared data
    app/air/                       runO2 planner
      noise.py                     resolution gate
      baseline.py                  federal modelled rasters
      conditions.py                weather, pollen, terrain
    docs/DATA_FIT.md               which data can carry the product
    experiments/                   viability and calibration evidence
```

The nested `basel-spatial-graph-main/basel-spatial-graph-v0/` path reflects the project's lineage from the earlier Basel Spatial Graph build. It is known cleanup debt, not an architectural requirement.

## Documentation

- [DATA_FIT.md](basel-spatial-graph-main/basel-spatial-graph-v0/docs/DATA_FIT.md) — which open datasets can carry runO2, and why
- [CLEAN_AIR_RUN.md](basel-spatial-graph-main/basel-spatial-graph-v0/docs/CLEAN_AIR_RUN.md) — the air layer's design
- [AIR_VIABILITY_REAL.md](basel-spatial-graph-main/basel-spatial-graph-v0/experiments/AIR_VIABILITY_REAL.md) — the gates on real data
- [Basel Spatial Graph](basel-spatial-graph-main/basel-spatial-graph-v0/README.md) — the graph underneath
- [ATTRIBUTION.md](ATTRIBUTION.md) — data sources and licences

---

Code: MIT ([LICENSE](LICENSE)). Committed data keep their upstream licences — Open Data Basel-Stadt, © Data BAFU / swisstopo, Open-Meteo, OpenStreetMap contributors and opentransportdata.swiss. See [ATTRIBUTION.md](ATTRIBUTION.md) for details.
