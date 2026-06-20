# Kickoff — Mapping / Brain + GeoReferencer

Your start-here for building your part of the system. You own the **probability map (the
brain)** and the **GeoReferencer**, and you're the **integration lead** — the only writer of
`MapState` and the point where the loop converges. Read this top to bottom once, then work the
build order in §5.

> **Priority: the brain is the focus.** The basic probability map is the shared foundation
> every other part — dashboard, detector, georeferencer — builds on, so it comes **first**.
> The GeoReferencer is **secondary**: don't start it until a basic map is up and running on
> mock observations.

---

## 1. What you own

- **The Brain — your primary job.** The probability map: build the prior, apply the Bayesian
  update on each observation (a detection sharpens belief; a clean pass over empty ground
  clears it), pick where to look next, and fire the `located` trigger when a detection is
  confident and persistent. This is the project's critical path and novel core — and the
  **shared foundation the dashboard, detector, and georeferencer all build on.** Get a basic
  version working before anything else.
- **The GeoReferencer — secondary.** Turns a pixel-space detection plus camera pose into ground
  cells, so a detection lands on the right map cell and a non-detection clears the right cells.
  Take it on **only once the basic map is solid** — until then the brain runs on mock
  observations, so geo isn't blocking anything.
- **Integration lead** — you hold the single-writer `MapState` and wire the loop together
  (detector → geo → brain → consumers). Integrate continuously, not at the end.

---

## 2. Read first (in order)

1. **`docs/interfaces.md`** — the contracts **and** the Bayesian update + `located`-trigger
   math (§5: `d_i`, the clipped likelihood ratio `LR(c)`, persistence `N`, `P_located`). This
   is the spine; everything you build conforms to it.
2. **`docs/prior_model.md`** — the prior you implement: `prior_i ∝ D(dist)·A·C`, with σ set
   from Koester's lost-person data.
3. **`docs/demo_scenario.md`** — the concrete runtime: the `GridSpec` instance (local UTM 10N,
   50 m cells, 160×160 ≈ 8×8 km), the scripted `CameraPose` flight path (use it to drive the
   georeferencer), and the expected map evolution (the trigger firing).
4. **`docs/tech_stack.md`** — the ratified libraries, so framework picks aren't re-litigated.

Then your two paste-ready prompts: **`prep/brain.md`** and **`prep/georeferencer.md`**.

Background already in `docs/`: `core_loop.md` (the one-glance flow), `build_plan.md` (the 24h
plan + your cluster + the gates), `SAR_project_plan.md` (the full design).

---

## 3. Environment setup

```
cp .env.example .env
```

For your part the only relevant key is `OPENTOPOGRAPHY_API_KEY`, and only if you re-fetch the
DEM — the terrain you need is already local:

- `data/terrain/dem_marin_usgs10m.tif` — elevation (the `D`/accessibility inputs).
- `data/terrain/worldcover_2021_N36W123.tif` — land cover (accessibility `A`).
- `data/terrain/osm_norcal.osm.pbf` — raw OSM; clip it to the demo AOI for the corridor term
  `C` (trails/roads).
- `data/behavior/koester_references.md` — the Koester stats that set σ.

`.env` is gitignored — never commit it.

---

## 4. Proposed scaffolding (create when you start — not pre-built)

Mirror the slice of the proposed layout that's yours (the full tree is in `docs/build_plan.md`):

- **`src/common/`** — the `GridSpec` and the shared contract types (`DetectorOutput`,
  `CameraPose`, `Observation`, `MapState`, `LocatedEvent`) from `interfaces.md`. You seed this
  because you're the single writer and integration lead — but it's the *shared* contract, so
  keep it reconciled with the team (see §6).
- **`src/geo/`** — the GeoReferencer (frame→ground projection, grid math).
- **`src/search/`** — the brain (prior construction, Bayesian update, `located` trigger,
  next-target selection).

Keep `MapState` **serializable** so it can cross a process/socket boundary later (e.g. Redis)
without a contract change.

---

## 5. Build order (your critical path)

The principle: **get the map moving on mock data first, then make the data real** (build_plan
P1 → P2). The milestone that matters is a **basic working probability map** (steps 1–3) that
the other parts can already consume; the GeoReferencer (step 4) is **secondary** and comes
after. In rough order:

1. **Lock `GridSpec` + the contract types** in `src/common`, taken from the `demo_scenario`
   instance (UTM 10N, 50 m, 160×160). This unblocks everything downstream — do it first.
2. **Brain on mock observations.** Implement the map + the Bayesian update so a *fake*
   observation visibly moves the map — a detection sharpens (clipped `LR`), a clean coverage
   pass clears. This is the highest-risk core; prove it early.
3. **Prior construction** from `data/terrain` + `data/behavior` (`prior ∝ D·A·C`, σ from
   Koester). The map's starting state.
4. **GeoReferencer (secondary — only once steps 1–3 give a working map).** Turn `DetectorOutput`
   + `CameraPose` → `Observation` (footprint cells + ground detections). Test it with a *mock*
   `DetectorOutput` + the demo flight path; you don't need the real detector to build this.
5. **Wire geo → brain, then integrate** with the detector owner at the `Observation` boundary.
   That's the integration-lead job — do it continuously. Target the ~h14 gate: a *real*
   detection moves the *real* map.

**Fallback (Tier B):** if the live update slips, the brain can run on a scripted `MapState`
sequence — keep that seam clean so the demo survives either way.

---

## 6. Integration-lead caveat (important)

You're building in a personal dir, but **`interfaces.md` is the team's shared source of
truth.** Keep your copy byte-identical with your teammates'. Any change to a contract (a field,
the `LR`/`d_i` form, the `GridSpec`) must be **re-ratified with the team and propagated** —
never edited locally in isolation, or integration breaks. The invariants that don't change: the
`GridSpec`, the data-flow direction, and single-writer `MapState`.

---

## 7. Driving Claude Code

- Open `prep/brain.md` (or `prep/georeferencer.md`) and paste its prompt into Claude Code — it
  explains its plan before building and waits for your go.
- **Build against the contracts, not against your teammates** — stubs first (a mock
  `Observation` for the brain; a mock `DetectorOutput` for the geo).
- **Tunables live in config, not code:** `recall`, `LR_max`, the `LR(c)` shape, `P_located`,
  persistence `N`, the prior weights, `cell_size_m`. Expect to tune them live.
