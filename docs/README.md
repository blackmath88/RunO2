# runO2

**Basel's trams measure the air. runO2 helps you plan a run around what they measured.**

runO2 is a Hack am Rhein warm-up project built on the Basel Spatial Graph. The intended product is a simple running-loop planner: choose a start point, distance and time; compare a small set of plausible loops by measured air-quality conditions; inspect weather, pollen, elevation and measurement coverage; then export the selected route as GPX.

## Current state

The repository currently contains:

- `basel-spatial-graph-clean-air-run.zip` — Claude-generated implementation package, still compressed and pending import into the repository tree.
- `docs/clean-air-run-concept.json` — product concept, viability gate, provenance model and MVP scope.
- `docs/deferred-extensions.json` — explicitly deferred ideas to prevent scope creep before the warm-up ships.
- `docs/runO2-ux-mock.html` — UX direction: cinematic intro, map-first planner, route alternatives and pre-run report.
- `docs/basel-wetter-reference.html` — visual/data reference for weather and air-quality integration.

## Product direction

The core interaction should stay narrow:

1. Pick a start point.
2. Choose how long/far you want to run and when.
3. Generate a few candidate loops.
4. Compare measured air conditions and measurement coverage.
5. Review a pre-run brief with weather, pollen and elevation.
6. Export GPX and go.

The differentiator is not generic route planning. It is the join between Basel air-quality measurements and the existing deterministic street graph, with provenance carried through every result. Unmeasured streets must remain visibly unmeasured.

## Immediate next steps

1. Unpack `basel-spatial-graph-clean-air-run.zip` into the repo root and inspect the generated implementation before changing architecture.
2. Run the existing tests / app locally and document what actually works.
3. Execute the air-data viability gate before investing in route optimisation.
4. Wire the UI around the smallest successful loop-generation and scoring path.
5. Add weather, pollen and elevation only after the core route comparison works.
6. Finish GPX export and provenance rendering.

See `docs/clean-air-run-concept.json` for the build sequence and scope boundaries.
