# GeoReferencer ↔ Detector — Integration Assumptions (Boundary A)

The detector is a **separate track**, so `interfaces.md §2` (`DetectorOutput`) is the
**expected** shape we build to, **not a guarantee**. This is the checklist to reconcile
with the detector owner *before* wiring the real detector in — and the seams that absorb
drift so reconciliation is small. Until then, the detector simulator (`src/demo/detector_sim.py`)
stands in, emitting the same `DetectorOutput`.

## Where the real detector plugs in
```
[real detector] -> DetectorOutput -> adapt_detector_output -> sanitize_detector_output -> GeoReferencer.reference -> Observation -> brain
                                     └──────────── boundary A (src/geo/georeferencer.py) ────────────┘
```
- **`adapt_detector_output(raw)`** is the drift seam. Today it passes a `DetectorOutput`
  through and raises on anything else. If the detector emits a different shape, map it to
  `DetectorOutput` **here** — nothing downstream changes.
- **`sanitize_detector_output`** then clips boxes to the image and drops NaN/off-frame
  detections (defense in depth — the detector is not assumed clean).

## Assumptions to confirm with the detector owner
1. **Representation.** Do they import our `DetectorOutput`/`Detection` dataclasses, or emit
   dicts / their own type / JSON? If not ours, we write the mapping in `adapt_detector_output`
   (a thin adapter, not a redesign).
2. **Box format.** We assume `bbox_xywh` = **(top-left x, y, width, height) in pixels**. If
   they emit `xyxy` (corners) or **normalized [0,1]** coords, convert in the adapter.
3. **Image resolution.** The bbox pixels must be in the **same resolution as the pose's
   `image_size_px`** (geo uses the pose's size as authoritative). If the detector runs at a
   different size (e.g. a resized/letterboxed input), scale boxes in the adapter.
4. **SAHI / tiling.** The detector plan uses SAHI sliced inference. We assume detections are
   **merged back to full-frame coordinates** (post-NMS), not per-tile. Confirm.
5. **`frame_id`.** Must match the `CameraPose.frame_id` exactly (the fusion join key).
   `GeoReferencer.reference` raises on a mismatch. Agree on the id format/format.
6. **`sensor_type`.** Enum values `"color"` / `"thermal"` (our `SensorType`). Confirm the
   detector tags frames the same way — it drives recall and the visibility sensor factor.
7. **`confidence`.** Raw score in `[0,1]`; the brain treats it as **uncalibrated/bucketed**
   evidence (§5.3), so the detector's exact calibration does **not** need to match anything —
   it never leaks past geo. (This is the big de-risk: the detector's hardest unknown is a no-op
   for us.)

## What is already absorbed (no reconciliation needed)
- **Geography / calibration isolation.** `sensor_type` and `confidence` pass *through* geo
  to the brain untouched; geo only does geometry. Whatever the detector's model/calibration,
  geo and the brain are unchanged (interfaces.md locked decision #1).
- **Messy output.** NaN confidence, boxes partly/fully off-frame, and (downstream) off-grid
  projected cells are handled by `sanitize_detector_output` and the brain's `sanitize_observation`.

## Honest baseline limits (geo side)
- Flat-ground, **nadir-centered** projection that **ignores the gimbal-pitch forward shift**;
  the feasibility harness measured this as ~18–24 m placement error at the demo's pitch — small
  enough that detections still land in the subject's cell. Perspective projection (using
  intrinsics + DEM) is the upgrade behind the same `reference()` seam.
