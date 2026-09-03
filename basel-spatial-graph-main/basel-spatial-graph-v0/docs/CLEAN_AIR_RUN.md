# Clean Air Run

A running-loop planner built on the walking network, scored by what tram-mounted
air sensors measured on each street — and explicit about the streets nobody has
ever measured.

Built for the Hack am Rhein warm-up. Additive: nothing in `app/` outside
`app/air/` changed except six guarded lines in `main.py` that mount the router.

---

## The gate

The committed fixture report exercises the gate on a synthetic field. The real
report is written separately to `experiments/AIR_VIABILITY_REAL.md`.

Before trusting any of it, run:

```bash
python -m app.air.viability --csv data/raw/air/100113.csv \
  --out experiments/AIR_VIABILITY_REAL.md
```

The viability script asks whether the data can carry the product at all:

| Question | Passes when | Fails how |
|---|---|---|
| **spatial** | Street-to-street differences exceed within-street spread at a fixed hour by 1.5x | No route recommendation is possible |
| **temporal** | Segment *rankings* change between morning and evening (rank disagreement ≥ 0.25) | Drop the hour control; one pattern is just moving up and down |
| **coverage** | More than 5% of segments have any reading | Coverage itself becomes the finding |
| **resolution** | Two streets differ by more than two sensors observing the same street in the same hour | The ranking is noise, and no amount of extra coverage fixes it |

A failing answer is a good outcome. It is much cheaper to learn in an hour that
the data cannot support a route recommendation than to discover it after
building an interface around one.

The spatial check compares streets **at a single hour**. Pooling across the day
would fold the morning-to-evening swing into the within-street spread and make
genuine differences look like noise — this was found by watching the fixture
fail a check it should have passed.

---

## Provenance

The repository already classifies values as observed / official / derived /
dynamic. Mobile sensor data forces one addition:

| Class | Meaning |
|---|---|
| `measured` | A sensor passed this street and read a value. Carries dataset, retrieval date, reading count, and error band where published. |
| `unmeasured` | No sensor ever passed. Unknown, **not** clean. |
| `dynamic` | The exposure total, computed for one pace and one hour. Carries its parameters. |

`unmeasured` is the load-bearing one and most of the test suite defends it:

- every segment appears in the output, including those with no readings
- an unmeasured segment never acquires a value
- it contributes nothing to an exposure total, and its share travels with that total
- a loop cannot rank as cleanest by virtue of being unknown — ranking is by
  exposure per measured minute, with measured share as tiebreak
- the GPX writer never emits a concentration for an unmeasured point

An interpolated surface would have been easier and would have quietly turned
ignorance into a recommendation.

---

## Exposure

```
exposure = Σ concentration × minutes_on_segment × ventilation
```

Pace belongs in the model, not just the display: a slower runner spends longer
breathing the same street. `VENTILATION_L_PER_MIN` is one round constant, not a
physiological model — putting a precise figure on one person's intake is a claim
this data cannot support.

The mean concentration is averaged over the **measured part only**, which is the
honest denominator.

---

## Loops

Not an optimiser, and it does not pretend to be. Waypoints on a circle around
the start, routed out and back, filtered to ±25% of the target distance, scored
and ranked. The interface says "candidates".

A better generator can replace `loops.py` entirely without touching anything
else — the only thing leaving that module is a list of node paths.

---

## GPX

`GET /run/gpx` returns GPX 1.1 that imports into Strava, Garmin, Komoot and
Apple Fitness with no OAuth, no API key and no terms review.

Provenance rides in the `<extensions>` block: per track point the concentration,
its class and the segment id; per track the total, the pace and hour assumed,
and the unmeasured share. GPX readers ignore extensions they don't understand,
so the file stays importable everywhere while anyone opening it in a text editor
can see where every number came from.

A portable record format for provenance-carrying activity data — on an open
protocol rather than in one page — is the obvious next step. It is not this
week's work.

---

## Layout

```
app/air/
  model.py              AirReading, SegmentAir, Coverage, the two new classes
  attribute.py          readings → segments, with coverage accounting
  exposure.py           scoring, pace scaling, the dynamic result
  loops.py              candidate generation
  gpx.py                GPX 1.1 + provenance extensions
  viability.py          the gates
  noise.py              the resolution gate: signal against instrument noise
  baseline.py           federal modelled rasters, clipped to Basel
  conditions.py         weather, pollen, AQI and smoothed terrain
  api.py                /run, /run/loops, /run/report, /run/conditions, /run/gpx
  testing.py            deterministic grid network
  sources/
    base.py             the contract
    fixture_source.py   synthetic field with a known spatial and temporal shape
    basel_tram.py       real adapter — SCHEMA UNVERIFIED, one dict to fix
app/static/run.html     the interface
app/static/runo2.js     its behaviour
tests/test_air_layer.py, tests/test_air_api.py
```

## Known limitations

- Dataset 100113's confirmed fields are `time`, `sensornr`, `pm25`, `pm10`,
  `longitude` and `latitude`. Stationary QA sensors 236 and 240 are excluded.
- **The resolution gate fails on the real data**, and this is the project's
  central finding. Signal 0.51 ug/m3 between two streets, noise 1.41 ug/m3
  between two sensors on the same street in the same hour: a ratio of 0.36
  where 1.0 is the minimum. The route ranking therefore runs on the federal
  NO2 raster (`app/air/baseline.py`), and the measured values are displayed
  beside it as corroboration rather than used to decide. See
  `docs/DATA_FIT.md` and `experiments/AIR_VIABILITY_REAL.md`.
- **The dataset is closed.** The campaign ran December 2019 to March 2020 and
  the publisher states it will never be updated. Nothing here describes today.
- The sensor error band stays `None`. The comparison dataset was read and does
  yield real figures for the low-cost class (bias -3.07 to -4.62 ug/m3, MAE
  4.65-5.85), but for a different sensor model in different years. Transferring
  it would be a made-up band wearing a citation.
- Attribution is midpoint-within-50m. Crude on purpose: the sensor is on a tram
  roof and finer precision would be false.
- Loops are candidates, not optima.
- Exposure compares routes. It is not a health claim and not a measure of what
  any individual inhales.
