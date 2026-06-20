# Kickoff — GeoReferencer

**What this is.** The one place geography lives. It ties each video frame to the ground area it
covered: consumes `DetectorOutput` + `CameraPose`, produces `Observation` (footprint cells + ground
detections) for the brain.

**Where this fits (build plan).** Cluster: **Perception → ground**. **High-risk / novel** — the
pixels→ground seam, with no off-the-shelf shortcut; one of the two places our real risk lives. Your
*first steps* below are **P1** (against mock detections + poses); be feeding the brain by the **~h14
gate**. Full arc/roles/gates: `docs/build_plan.md`.

**Read first.** `docs/interfaces.md` **§1** (`GridSpec`), **§2** (`DetectorOutput` in), **§3**
(`CameraPose` in), **§4** (`Observation` out, incl. the frame-to-ground method).

**Build against (contracts).** Consume `DetectorOutput` + `CameraPose` (joined by `frame_id`) →
produce `Observation`. Reference the shared `GridSpec`.

**First steps (stubs-first).**
1. `GridSpec` conversions (`latlon_to_cell` / `cell_to_latlon`).
2. Camera **footprint**: project the frame's coverage onto ground cells, with `coverage_fraction`
   and `visibility_weight` per cell. Start linear/approximate; full perspective projection is a
   later upgrade.
3. Project each detection's bbox center to a ground cell.
4. Emit `Observation` (`footprint[]`, `detections_ground[]`, `sensor_type`). A non-detection is a
   footprint with an empty `detections_ground` — coverage matters as much as detections.

**Stub & test data.** Mock `DetectorOutput` + `CameraPose` along a short scripted flight path.

**Constraints.** Geography lives **only** here. Keep fidelity simple first (linear footprint),
upgrade later. Don't leak grid/geography back into the detector.

**Deliverable.** An `Observation` stream the brain can consume — footprints that cover cells, and
detections that land on the right cell.

---

### Paste-ready prompt

> You are building the **GeoReferencer** for our search-and-rescue system — the only component that
> knows geography. It consumes `DetectorOutput` + `CameraPose` and produces `Observation` for the
> brain. First read `docs/interfaces.md` §1–§4 (`GridSpec`, `DetectorOutput`, `CameraPose`,
> `Observation` and the frame-to-ground method). **Explain your plan before writing code, and wait
> for my go.**
>
> Then build, stubs-first, in `src/geo/` (shared types in `src/common/`):
> 1. `GridSpec` conversions (`latlon_to_cell` / `cell_to_latlon`).
> 2. A camera-footprint projection from `CameraPose` onto ground cells, with `coverage_fraction` and
>    `visibility_weight` per cell (linear/approximate is fine to start).
> 3. Projection of each detection's bbox center to a ground cell.
> 4. Emit `Observation` per `interfaces.md` §4 (footprint + ground detections + sensor_type); a
>    covered frame with no detections is a valid non-detection observation.
>
> Drive it with **mock `DetectorOutput` + `CameraPose`** along a short scripted path. Geography lives
> only here — never push grid/lat-lon back into the detector. Hold the `Observation` contract exactly
> as ratified.
