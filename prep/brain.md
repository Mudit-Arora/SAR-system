# Kickoff — The Brain (search map + Bayesian update)

**What this is.** The project's center of gravity and the **critical path**: the probability map
over the region, the Bayesian update that moves it, and the search direction it produces. It is the
**single writer of `MapState`**.

**Where this fits (build plan).** Cluster: **Brain + integration lead — the critical path and the
highest-risk component**; it gets the strongest owner. You **own and write `MapState`** (the *only*
writer); if the surfaces run as separate processes, publish it via **Redis** at the P2 integration
step. Your *first steps* below are **P1** (build on mock `Observation`s); be integrated by the **~h14
gate** (a real detection moves the real map). **Safety net:** if the live update slips, the demo
falls back to a scripted `MapState` (Tier B). Full arc/roles/gates: `docs/build_plan.md`.

**Read first.** `kickoff.md` (this dir's start-here + priority) · `docs/interfaces.md` **§4** (your
input `Observation`), **§5** (your core math), **§6** (your outputs `MapState` / `LocatedEvent`) ·
`docs/prior_model.md` (the prior) · `docs/demo_scenario.md` (the runtime beats).

**Build against (contracts).** Consume `Observation`; own and write `MapState`; emit `LocatedEvent`.
You are the only writer of state.

**First steps (stubs-first).**
1. `GridSpec` + a prior probability map from terrain / vegetation / last-known-position /
   lost-person behavior (per `prior_model.md`), with reserved out-of-region mass `p_out`.
2. The per-cell update (`interfaces.md` §5): non-detection `p_i ← p_i·(1 − d_i)`; detection
   `p_k ← p_k·LR(c)·kernel(k,i)`; renormalize over cells **and** `p_out`. `d_i` =
   coverage×visibility×recall; `LR(c)` clipped + bucketed.
3. A `predict()` → `update()` loop seam (`predict()` a no-op for now — stationary subject).
4. The `located` trigger: aggregated posterior over a window ≥ `P_located` **and** persistence across
   `N` overlapping frames. Do **not** re-multiply `LR` per frame for the same blob. Emit
   `LocatedEvent` when it trips.
5. Maintain `MapState` (`posterior`, `coverage`, `top_cells`, `next_target`, `status`).

**Stub & test data.** A mock `Observation` stream — a handful of frames with footprint cells and one
planted detection — so the loop runs before the real GeoReferencer exists.

**Constraints.** Single writer of `MapState`. Tunables in config, not code. Keep the contracts
stable. The stationary-subject assumption is fine for the demo — just leave the `predict()` seam.

**Deliverable.** A running loop where mock `Observation`s move the posterior, non-detections clear
coverage, and a persistent detection flips `status` to `located` and emits a `LocatedEvent`.

---

### Paste-ready prompt

> You are building the **search-map brain** for our wide-area search-and-rescue system — the
> critical path and the single writer of `MapState`. First read `kickoff.md` (this dir's start-here
> + priority), then `docs/interfaces.md` §4–§6 (input `Observation`, the math in §5, outputs
> `MapState` and `LocatedEvent`) and `docs/prior_model.md` (the prior). **Explain your build plan and
> module layout before writing code, and wait for my go.**
>
> Then build, stubs-first, in `src/search/` (shared types in `src/common/`):
> 1. A `GridSpec` and a prior probability map from terrain / last-known-position / lost-person
>    behavior (per `prior_model.md`), with reserved out-of-region mass `p_out`.
> 2. The Bayesian per-cell update from `interfaces.md` §5: non-detection `p_i ← p_i·(1−d_i)`;
>    detection `p_k ← p_k·LR(c)·kernel(k,i)`; renormalize over cells **and** `p_out`. `LR(c)` clipped
>    and bucketed; `d_i` = coverage × visibility × recall.
> 3. A `predict()` → `update()` loop seam, with `predict()` a no-op for now.
> 4. The `located` trigger: aggregated posterior over a window ≥ `P_located` **and** persistence
>    across `N` overlapping frames; do **not** re-multiply `LR` per frame for the same blob. Emit a
>    `LocatedEvent` when it trips.
> 5. Maintain `MapState` (posterior, coverage, top_cells, next_target, status) — you are its only
>    writer.
>
> Drive it with a **mock `Observation` stream** (a few frames including footprint cells and one
> planted detection) so it runs before the real GeoReferencer exists. Put every tunable (`recall`,
> `LR_max`, `LR(c)` buckets, `P_located`, `N`, kernel width, `p_out`, `cell_size_m`) in config, not
> code. Keep the `Observation` / `MapState` / `LocatedEvent` contracts exactly as ratified.
