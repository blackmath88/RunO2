# Status

The implementation is unpacked and running. `basel-spatial-graph-clean-air-run.zip`
is gone from the tree; its contents live in
`basel-spatial-graph-main/basel-spatial-graph-v0/`.

**Working:** the planner at `/run` on the real 19,258-segment Basel walking
network, ranked by the federal NO₂ raster, with measured tram PM2.5 shown
beside it; weather, AQI, pollen and smoothed terrain; GPX export with
provenance; 434 tests passing.

**Established:** the tram dataset cannot rank routes — see the resolution gate
in `experiments/AIR_VIABILITY_REAL.md` and the full argument in
`basel-spatial-graph-v0/docs/DATA_FIT.md`.

## Proposed repository cleanup

Not yet applied. It is mechanically safe — nothing in the application resolves
paths above its own root, and the suite passes from
`basel-spatial-graph-v0/` regardless of where that sits — but it rewrites every
path in the repository, so it wants its own commit rather than being folded
into feature work.

`basel-spatial-graph-main/` is a pure wrapper: it holds the application plus
`README.md`, `ATTRIBUTION.md` and `LICENSE`, all three byte-identical to the
copies at the repository root.

```
git rm basel-spatial-graph-main/{README.md,ATTRIBUTION.md,LICENSE}   # exact duplicates
git mv basel-spatial-graph-main/basel-spatial-graph-v0/* .           # promote the app
git mv basel-spatial-graph-main/basel-spatial-graph-v0/.gitignore .  # merge into root
rmdir basel-spatial-graph-main/basel-spatial-graph-v0 basel-spatial-graph-main
```

Two collisions to resolve by hand:

- **`README.md`** — the root one (runO2, this project) must win; the
  application's own 36 kB README moves to `docs/SPATIAL_GRAPH_README.md`.
- **`docs/`** — the two directories merge cleanly; no filename appears in both.

Afterwards, update the paths in the root `README.md` links and in
`docs/README.md`. Use `git mv` throughout so history follows the files.

The upstream Basel Spatial Graph attribution in `ATTRIBUTION.md` stays exactly
as it is — the parent project's provenance is not ours to drop.
