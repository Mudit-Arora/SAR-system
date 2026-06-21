# Integration Kickoff — Wiring the teammates' tracks into the brain core

**Start-here guide for the integration work session.** Goal: combine the three tracks
(**brain** = ours/core, **detector** = YOLO, **dashboard** = React UI, plus **voice** later) into
one running system on an `integration` branch, with the **brain as the core** — real detections
flow into the probability map and a live React dashboard renders it. End state: push to `main` /
an integrated branch once it runs end-to-end.

> Read this first, then the locked plan it summarises (the session plan file), plus
> `docs/interfaces.md` (the ratified contracts — the integration SEAMS) and
> `docs/brain_followups.md` (honest limitations). Explain your approach before building
> (per `~/.claude/CLAUDE.md`), and **checkpoint after each unit**.

---

## Where we are
The **brain track is feature-complete, tested, committed** (branch `brain`): probability map
(prior → Bayesian update → `located` trigger, single-writer `MapState`), GeoReferencer, real-raster
terrain, the real-terrain showcase, and **C1 sectorized + multi-drone search** (`src/search/planner.py`,
`src/demo/search_demo.py`). 121 tests green. The seams the teammates plug into already exist:
the `DetectorOutput` geo boundary (`docs/interfaces.md` §2), the serializable `MapState` /
`MapState.to_dict()`, and `LocatedEvent`.

**The teammates' tracks** live on sibling branches of the same repo (`Mudit-Arora/SAR-system`),
inspected via the GitHub API:
- **`detection`** branch (SHA `f1aaaf2…`): a Python **YOLO CLI** (`src/sar_demo/infer_video.py`).
  Emits its OWN `Detection(xyxy, conf, cls_id, class_name, track_id, …)` per frame, has its own
  centroid tracker, and is **geography-blind** (no telemetry). Deps: `ultralytics`, `opencv-python`.
  **No `best.pt` weights committed** (`runs/`/`models/` are `.gitkeep`).
- **`dashboard`** branch (SHA `c5fabcb…`): a **React/TS/Vite** app driven 100% by a static
  `src/data/mockState.ts` (`App.tsx` imports it directly). Its `MapState` (`src/types.ts`) is a UI
  **view-model** (normalized 0..1 `pos`, `heatBlobs`, `telemetry`, UI `Detection[]`, `stats`/`trend`/
  `loop`) — **completely different** from the brain's `MapState` (posterior grid, cells, `p_out`).
  The same branch also holds the **voice** service dir (`deepgram-voice-agent-inbound-telephony/`).
- **voice** (on the `dashboard` branch): a Twilio+Deepgram **inbound telephony** agent, currently a
  generic appointment-scheduling template with a clean backend-swap seam.

---

## Locked decisions (do not relitigate)
1. **Order:** **Milestone 1 = detector + dashboard** (the visible loop). Voice = Milestone 2.
2. **Telemetry:** **script poses** — pair each footage frame with a scripted `CameraPose` (reuse
   `src/demo/mock_stream.py`). Honest caveat: geo placement is approximate (assumed path, not GPS).
3. **Layout:** **monorepo on an `integration` branch off `brain`**, each track **vendored** into its
   own top-level dir (NOT branch-merged), plus a new `integration/` glue package. `main` untouched
   until end-to-end green.
4. **Detector wiring:** **in-process adapter** — import YOLO per-frame inference → brain `DetectorOutput`.

---

## The discipline (the point — protect functionality, avoid rewrites/conflicts)
1. **Adapters at the seams; never rewrite either side.** ALL translation lives in `integration/`.
   Teammate code is vendored as-is; the brain's `src/` is touched only *additively* (the seams
   already exist). The one teammate-side edit is swapping the dashboard's data source — done
   **additively** (a hook with a mock fallback).
2. **Two canonical contracts, bridged by ONE projection.** Brain Python contracts = canonical for
   the LOOP; dashboard TS types = canonical for the UI. **Don't unify** — bridge with a single
   `MapState → UI-MapState` projection. Drift is isolated to two adapters, not smeared across files.
3. **Vendor, don't merge.** `git archive` each track into its own dir (no branch merge → no conflicts
   on shared root docs / no `src/` collision; teammates keep evolving their branches).
4. **Incremental — verify each seam before the next:** detector→brain → projection+server →
   dashboard. Don't wire the next until the current is green.
5. **Integration branch only; `main` untouched until end-to-end green.**

---

## Repo setup (first steps)
- `git checkout -b integration brain` (brain is the core).
- Vendor each track (plain files, history-light — fine for a hackathon):
  ```bash
  mkdir detector      && git archive detection | tar -x -C detector
  mkdir dashboard_app && git archive dashboard dashboard | tar -x --strip-components=1 -C dashboard_app
  mkdir voice         && git archive dashboard deepgram-voice-agent-inbound-telephony | tar -x --strip-components=1 -C voice
  ```
  Keep the brain's `docs/` as canonical; drop teammates' duplicate root docs. Commit as one
  "vendor detector/dashboard/voice at <SHAs>" commit (record SHAs above).

---

## The build — Milestone 1 (the `integration/` glue, a new Python package)
1. **`integration/detector_adapter.py`** — YOLO per-frame inference → brain `DetectorOutput`.
   Factor a small `infer(frame)` out of the detector CLI (or load `ultralytics.YOLO(model)` and call
   `.predict(frame)`); convert `xyxy → bbox_xywh`; wrap in `DetectorOutput(frame_id, timestamp,
   detections, model_id, sensor_type)`. **Keep `sensor_type`/footage kind PARAMETERS** (see Weights
   note). This is the adapter the geo boundary (`docs/interfaces.md` §2) was designed for.
2. **`integration/telemetry.py`** — a `CameraPose` per frame index along a scripted path. Reuse
   `build_scripted_path` / `sweep_pose` (`src/demo/mock_stream.py`). Pair frame i → pose i.
3. **`integration/loop.py`** — orchestrator: footage → `detector_adapter` → `GeoReferencer`
   (`src/geo`) → `SearchBrain` (`src/search/brain.py`), emitting `MapState` / `LocatedEvent`. Mirrors
   `src/demo/run.py` wiring with the real detector + scripted poses.
4. **`integration/dashboard_projection.py`** — brain `MapState` → the dashboard's UI `MapState`
   (target shape = `dashboard_app/src/types.ts` / `mockState.ts`): downsample `posterior` →
   `heatBlobs`, cells → normalized `pos`/`flightPath`/`dronePos`, `detections_log` → UI `Detection[]`,
   derive `stats`/`telemetry`/`trend`/`loop`/`confidenceToDeclare`.
5. **`integration/server.py`** — a tiny **FastAPI** app: run/step the loop, serve `GET /state` →
   UI-MapState JSON (polling), plus the latest `LocatedEvent`. CORS for the Vite dev server.
6. **Dashboard data swap (additive):** add `dashboard_app/src/hooks/useMapState.ts` that polls
   `/state`, falling back to `mockState` when offline; swap `App.tsx`'s `mockState` for the hook.

## Milestone 2 — voice (workaround first; full telephony strictly gated)
- **Workaround (default):** **TTS the brain's `LocatedEvent` broadcast line into the dashboard.** It
  already has `VoiceComms`/`LiveTranscript`; feed them the broadcast text via `dashboard_projection`
  (add `recentCommands`/a transcript entry) and speak it with the browser **Web Speech API**
  (`speechSynthesis`, zero deps). Demos "voice" in the visible loop for almost nothing.
- **Full telephony agent — STRICTLY GATED:** attempt the real Deepgram/Twilio agent **only if every
  other integration is already working end-to-end**, never at the expense of the core. If attempted:
  swap the telephony `scheduling_service` for a `sar_service` reading the brain state via the API and
  rewrite `agent_config.FUNCTIONS` to SAR (highest-probability area, coverage %, status).

---

## Libraries (justify before adding, per CLAUDE.md)
- **FastAPI + uvicorn** — *what:* an async Python web framework. *Why here:* the lightest thing that
  serves the UI-MapState as JSON to the React app now AND gives WebSocket/streaming for free if
  voice/live-push arrives later. *Simpler alt:* Flask (sync, fine for polling) — pick at build time;
  FastAPI wins only if we expect WS. *No other new Python deps* beyond the detector's
  (`ultralytics`/opencv). Dashboard is its own Node toolchain (`npm`).

## Files
- **New:** `integration/` (`detector_adapter.py`, `telemetry.py`, `loop.py`, `dashboard_projection.py`,
  `server.py`), `tests/test_integration_*.py`, `dashboard_app/src/hooks/useMapState.ts`.
- **Vendored (as-is):** `detector/`, `dashboard_app/`, `voice/`.
- **Modify (additive):** `dashboard_app/src/App.tsx` (one import swap); `requirements.txt` (detector +
  FastAPI deps).
- **Reuse:** the geo `DetectorOutput` boundary (`src/geo`), `SearchBrain` (`src/search/brain.py`),
  `MapState.to_dict()` (`src/common/contracts.py`), `build_scripted_path`/`sweep_pose`
  (`src/demo/mock_stream.py`), the loop wiring in `src/demo/run.py`.

## Verification (Milestone 1, end to end)
- **Detector adapter** (unit test): synthetic frame → valid `DetectorOutput`; `xyxy→xywh` correct;
  empty frame → empty detections (the non-detection signal).
- **Loop**: `python -m integration.loop` on demo footage + scripted poses → the map updates on real
  detections (ideally locates); mass invariant `posterior.sum() + p_out == 1` holds.
- **Projection** (unit test): brain `MapState` → UI dict satisfying `types.ts` (keys + `pos`/`heatBlobs`
  in [0,1]).
- **Server**: `uvicorn integration.server:app`; `curl /state` → valid UI JSON.
- **Dashboard**: `cd dashboard_app && npm install && npm run dev` pointed at the server → live render.
- Brain's own `pytest` stays green (brain `src/` only touched additively).

## Risks / resolve early
- **Weights + modality (TBD by teammate):** no `best.pt` yet; teammate is still choosing the dataset
  and **thermal vs RGB**. So keep the pipeline **modality-agnostic** (`sensor_type`/footage kind as
  parameters). Develop against pretrained **`yolo11s.pt`** (COCO, has "person"); swap in `best.pt`
  later — a `model_id` swap, minimal effort.
- **Heavy deps:** the detector pulls `ultralytics`/torch/opencv (large install); brain stays light.
- **Telemetry approximation:** scripted poses ⇒ geo placement is assumed, not measured — state honestly.
- **Footage ↔ pose alignment:** tune the scripted path so detections land in sensible cells.

## Reference
- Source branch SHAs to vendor: detection `f1aaaf2`, dashboard `c5fabcb` (`git ls-remote origin`).
- Detector run example: `python -m sar_demo.infer_video --model best.pt --video … --conf 0.25 --imgsz 960`.
- Update memory ([[integration-plan]], [[advanced-visual-demo-goal]]) as integration lands.
