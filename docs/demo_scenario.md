# Demo Scenario & Scripted Flight Path

**Status: pre-event design draft.** This is the concrete walkthrough the demo runs on. Its job
is to make every component's inputs real at once — the prior, the search path, the detections,
the map updates, and the voice beats — and to define the **scripted-path data format** the
GeoReferencer consumes. It is consistent with the contracts in `docs/interfaces.md` and the
demo beats in `SAR_project_plan.md` §9.

> **No-build rule.** This document is design only. The *runnable* `demo/` scenario config (the
> actual per-frame waypoint table the pipeline reads) is a pipeline input and is authored
> Saturday. Here we fix the **format** and a **worked, illustrative example**.
>
> **All coordinates and numbers below are illustrative**, chosen to be plausible for the chosen
> region and to tell a clean search story. Geography is finalized when the AOI is drawn
> (`docs/data.md`); behavior numbers are replaced by the Koester data (Tier-1 gather).

---

## 1. Region instance (`GridSpec`)

The search region is a focused sub-area of the expanded-Marin AOI, around the Mount
Tamalpais / Steep Ravine corridor — forested canyon, open coastal ridge, and trails down to
the coast, so the map shows real visibility contrast.

| `GridSpec` field | Illustrative value | Note |
|------------------|--------------------|------|
| `crs` | local UTM (zone 10N) | Equal-area cells, Euclidean math (per `interfaces.md` §1). |
| `origin` (SW corner) | ≈ (37.87, -122.66) | Finalize against the drawn AOI. |
| `cell_size_m` | **50** | Recommended start. A ~100–140 m frame footprint then spans several cells, so coverage tracking is meaningful. Tunable. |
| `n_rows` × `n_cols` | 160 × 160 | ⇒ an 8 km × 8 km search region (~25.6k cells; trivial for array math). |

A single incident's search region is only a few km across (lost hikers are usually found within
a couple km of the last-known position), so an 8 km box comfortably contains the scenario with
margin. The broader AOI data can cover more without enlarging the grid.

---

## 2. Incident setup

| Element | Illustrative value | Why it matters |
|---------|--------------------|----------------|
| Subject profile | Adult day hiker (Koester category "Hiker") | Best-studied behavior; gives a defensible prior. |
| Last-known position (LKP) | Pantoll trailhead ≈ (37.905, -122.605) | Anchors the prior. |
| Elapsed time | ~4 h overdue, reported near dusk | Dusk motivates the thermal / low-light story. |
| Terrain | Doug-fir/redwood canyon (Steep Ravine) + open coastal scrub | Mixed canopy ↔ open = visible variation in clearance. |

**Behavior assumptions (illustrative, replace with Koester numbers):** hikers tend to travel
downhill and downstream, follow trails then drainages, and are often found within ~2 km of the
LKP. These shape the prior; they are not invented at build time.

---

## 3. Prior sketch (what the judge sees first)

At `t0` the map shows probability blooming around the LKP, **elongated downhill along the Steep
Ravine drainage toward the coast**, following trail corridors, and **suppressed on steep
cliffs and across ridgelines** (hard to traverse). A small mass `p_out ≈ 0.07` is reserved for
"left the search region." The read: *the system believes the hiker most likely descended the
canyon toward the water* — a specific, explainable starting hypothesis, not a uniform blob.

(The concrete combination rule — `prior_i ∝ D(dist to LKP) × accessibility_i × corridor_i`,
normalized with `p_out` — is fully specified in `docs/prior_model.md`.)

---

## 4. True subject placement

The subject is actually **off-trail, partway down Steep Ravine, on a steep forested slope under
partial canopy**, ≈ 1.8 km downhill/SW of the LKP.

Chosen deliberately so the Bayesian update is *meaningful, not trivial*:
- **Consistent with downhill-drainage behavior**, so the prior gives this area *moderate* (not
  top) probability — the update has to do real work to lock on.
- **Under partial canopy**, which motivates the `visibility_weight` term and the thermal pass.
- **Off-trail**, explaining why ground teams hadn't found them.

---

## 5. Scripted flight path & its data format

The path is **map-directed**: it begins over the highest-prior corridor (down-canyon from the
LKP), sweeps it in a boustrophedon ("lawnmower") pattern, visibly clears cells via
non-detections, then reaches the subject's slope and corroborates.

### 5.1 Scripted-path record format (refines `interfaces.md` §3 `CameraPose`)

The demo's scripted path is an ordered list of per-frame records. This is the format the
`demo/` config will materialize (CSV or JSON) and the frame source + GeoReferencer will read.

| Field | Type | Meaning |
|-------|------|---------|
| `frame_id` | id | e.g. `F0001`; join key to the detector output. |
| `timestamp` | time | Monotonic sim clock. |
| `drone_lat`, `drone_lon` | float | Camera position. |
| `altitude_agl_m` | float | Height above ground; sets ground sample distance. |
| `heading_deg` | float | Direction of travel / camera azimuth. |
| `gimbal_pitch_deg` | float | −90 = nadir (straight down). |
| `hfov_deg`, `vfov_deg` | float | Horizontal/vertical field of view. |
| `image_w_px`, `image_h_px` | int | Frame size, for pixel→ground mapping. |
| `footage_ref` | string? | Which real footage file/frame backs this scenario frame (§6). Empty ⇒ a clean non-detection frame. |

### 5.2 Footprint sanity check

At `altitude_agl_m = 100`, `hfov_deg = 70`, near-nadir: ground width ≈ `2 · 100 · tan(35°) ≈
140 m`; at 16:9 the swath is ≈ 140 m × 80 m. Over a 50 m grid that's ≈ 3 × 2 = ~6 cells per
frame — enough overlap that coverage accumulates smoothly across a sweep.

### 5.3 Worked example (illustrative rows, not the full path)

| frame_id | t (s) | drone_lat | drone_lon | alt_agl_m | heading | gimbal | hfov | footage_ref | segment |
|----------|-------|-----------|-----------|-----------|---------|--------|------|-------------|---------|
| F0001 | 0 | 37.9040 | -122.6060 | 100 | 210 | −85 | 70 | — | start over LKP corridor |
| F0010 | 90 | 37.9008 | -122.6105 | 100 | 210 | −85 | 70 | — | sweeping down-canyon |
| F0024 | 216 | 37.8975 | -122.6150 | 100 | 230 | −85 | 70 | — | last clean sweep frame |
| F0027 | 243 | 37.8968 | -122.6165 | 95 | 230 | −80 | 70 | clipA:0027 | **over subject — detection** |
| F0032 | 288 | 37.8966 | -122.6168 | 80 | 235 | −75 | 70 | clipA_thermal:0005 | loiter / thermal corroboration |

Full path ≈ 35–45 frames over a few simulated minutes. The exact rows are authored Saturday;
this fixes the shape.

---

## 6. Footage → scenario mapping

The detector runs on **real footage**, but the footage's own geography is irrelevant — only the
scenario `CameraPose` determines where a detection lands on *our* map. The mechanism:

1. Each scenario frame is backed by a footage frame via `footage_ref`.
2. We **arrange the scripted path so that the frames whose backing footage contains a person
   are positioned over the subject's cell.** (e.g. a clip with a person visible in its frames
   25–30 is mapped to path frames F0027–F0031, which sit over the subject's slope.)
3. When the detector fires on that footage frame, the GeoReferencer projects its pixel box
   through the scenario `CameraPose` onto the subject's ground cell (+ kernel).
4. Frames with no person (or `footage_ref` empty) are clean non-detections that clear area.

This is the plan's "assign it along a scripted flight path," and why footage and map geography
need not match.

---

## 7. Detection / non-detection sequence

| Frames | Backing footage | Detector result | Map effect |
|--------|-----------------|-----------------|-----------|
| F0001–F0024 | no person | non-detections | high-prior corridor cells dim; coverage rises; mass shifts to remaining high-prior cells + small `p_out` rise |
| F0027–F0030 | person (color, partial canopy) | detection, conf ≈ 0.55–0.70 | subject cell brightens sharply (clipped LR + kernel); **status still `searching`** — persistence not yet met |
| F0031–F0034 | person (thermal pass) | detection, conf ≈ 0.80+ | adjacent/again hits; persistence `N = 3` met **and** windowed mass crosses `P_located` ⇒ **`located`** |

Persistence is confirmation logic *on top of* the posterior, not repeated `LR` multiplication
(per `interfaces.md` §5.4) — so the correlated color+thermal hits of the same subject don't
over-concentrate the map.

---

## 8. Expected map evolution (beat by beat)

1. **`t0` — prior.** Probability blooms down the canyon from the LKP.
2. **Sweep.** Cleared corridor cells dim; mass redistributes to remaining high-prior cells and
   nudges `p_out` up — the map visibly *reasons* about where is left to look.
3. **First detection (F0027).** Subject cell spikes (clipped, so it doesn't collapse the map);
   status remains `searching`.
4. **Corroboration (F0031–F0034, thermal).** Mass concentrates; `located` trips.
5. **Lock.** The high-probability region locks onto the subject; `LocatedEvent` emitted.

---

## 9. Voice beats

- **Operator (hands-free), during the sweep.** Query: *"Where's the highest-probability area?"*
  → answered from `MapState`: *"Highest probability is along the Steep Ravine drainage, about
  1.5 km southwest of the trailhead."* (Proves the system runs in the field.)
- **Subject broadcast, on `LocatedEvent`.** Composed from the event + map state, spoken through
  the simulated drone: *"We've located a person near Steep Ravine. Stay where you are — a
  ground team is on the way to your position. If you can hear this and it's safe, move toward
  open ground."* Plus a **second-language variant** (e.g. Spanish), which is near-free because
  the message is generated, not recorded. (The emotional high point.)

---

## 10. Mapping to the `SAR_project_plan.md` §9 demo

| §9 demo step | Scenario beat |
|--------------|---------------|
| 1. Region loads with an explained prior | §3 / beat 1 |
| 2. Drone searches a map-directed path | §5 / beat 2 |
| 3. Detector finds a probable person | §7 / beat 3 |
| 4. Map updates live, high-prob shifts | §8 / beats 3–4 |
| 5. System speaks to the subject (2nd language) | §9 subject broadcast |
| 6. Operator runs a step hands-free | §9 operator beat |

---

## 11. Decisions this surfaces (recommended defaults, for the team to ratify)

| Choice | Recommended default | Notes |
|--------|---------------------|-------|
| Subject category | Hiker | Best-studied behavior. |
| `cell_size_m` / region | 50 m / 8 km² (160²) | Balance of detail vs compute. |
| Path length / arc | ~40 frames, clear-then-find | Builds tension, shows clearing + finding. |
| Persistence `N` | 3 frames | Guards the broadcast from a single false positive. |
| Altitude AGL | ~100 m | ~140 m footprint; several cells/frame. |
| `p_out` seed | ~0.07 | Chance the subject left the region. |
| Backing footage clip | TBD | Depends on sourced footage (Tier-1). Pick a clip with a clearly detectable person for the detection frames. |
