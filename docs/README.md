# runO2 — concept and design direction

**Basel's trams measured the air. runO2 asks whether that data can plan a run.**

This directory holds the product thinking. The implementation, the evidence and
the data analysis live in `../basel-spatial-graph-main/basel-spatial-graph-v0/`.

## Files

- `runO2-ux-mock.html` — UX direction: cinematic intro, map-first planner, route
  alternatives, pre-run report. Implemented in `app/static/run.html`.
- `basel-wetter.html` — visual and data reference for the conditions layer.
  Implemented, narrowed to run-relevant values, in `app/air/conditions.py`.
- `clean-air-run-concept.json` — product concept, viability gate, provenance
  model, MVP scope.
- `deferred-extensions.json` — ideas deliberately not built, to stop scope creep.
- `STATUS.md` — where the build actually is, and the proposed repo cleanup.

## The interaction

1. Pick a start point.
2. Choose distance, pace and hour.
3. Generate candidate loops.
4. Compare air quality and measurement coverage.
5. Review a pre-run report: air, conditions, pollen, terrain, provenance.
6. Export GPX.

## What the project turned out to be about

The differentiator was never route planning. It is the join between Basel's open
air data and a deterministic street graph, with provenance carried through every
result — and, as it turned out, an honest account of where that data stops being
able to answer.

The tram dataset inspired the project and cannot carry it: two sensors on the
same street in the same hour disagree by more than two different streets do.
That finding is the product as much as the planner is. Both halves ship
together, in one page.

See **`../basel-spatial-graph-main/basel-spatial-graph-v0/docs/DATA_FIT.md`**.
