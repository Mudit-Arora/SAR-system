# Technology Stack — Decisions & Justifications

**Status: pre-event recommendations, to ratify Saturday.** These are the framework/library
choices for the three component tracks that needed one: the **dashboard**, the **voice stack**,
and the **detector**. Each follows the "what it does / why it fits / simpler alternative
considered / why not" format. Nothing is built before Saturday; this is the decision record so
the build doesn't burn time choosing.

These supersede the "provisional, not decided" notes in `SAR_project_plan.md` §8.

---

## 1. Dashboard / map renderer

**Decision: a Streamlit app rendering the probability grid as a colormapped image overlay on a
slippy map, refreshed by a fragment timer. Fallback: a plain Plotly/Matplotlib heatmap in the
same Streamlit shell.**

- **What it does.** Streamlit turns a Python script into a web app (no JS/build step). The
  160×160 probability grid is colormapped to an RGBA image and drawn as a georeferenced
  `ImageOverlay` on an OpenStreetMap base (via `st_folium`), with detection markers, the drone
  path, and alerts as extra layers. An `@st.fragment(run_every=...)` re-runs only the map block
  each tick.
- **Why it fits.** The grid is ~25,600 cells — *tiny* by mapping standards, so rendering
  performance is never the bottleneck; the real costs are (a) how live updates reach the screen
  and (b) frontend standup for an ML-leaning team. Streamlit minimizes both: pure Python, and a
  160×160 float grid is most naturally one colormapped image pushed per frame, not 25k polygons.
  It looks credible to judges (real basemap + terrain + markers) and maps directly onto the
  Python backend with no JS bridge. *(Maps to: lightest thing that works, explicit over clever,
  low frontend overhead.)*
- **Simpler alternative considered.** A plain Matplotlib/Plotly heatmap with the DEM as a
  background image, *no* slippy basemap — fastest of all to ship. It's the **fallback**: if the
  overlay alignment or map widget eats time, drop to `imshow`/`go.Heatmap` in the same Streamlit
  refresh loop and lose only pan-zoom roads. Because both live in one Streamlit app, downgrading
  is a swap of the render function, not a rewrite (clean seam).
- **Heavier alternatives rejected.** MapLibre GL JS / raw deck.gl give sub-second smoothness and
  a higher visual ceiling (3D terrain) but cost *days* of JS plumbing — wrong for a weekend ML
  team. `pydeck`-in-Streamlit is the middle ground (deck.gl visuals from Python) but has known
  live-refresh/view-reset quirks; consider only if someone wants the 3D-terrain wow-shot and
  accepts the fiddliness. kepler.gl and folium-as-the-live-engine are wrong for a per-frame
  updating view (kepler de-prioritizes streaming; folium regenerates static HTML per frame).
- **The one tradeoff to say out loud.** Streamlit's update model is **server-rerun, not push** —
  "live" at ~1–4 fps, not sub-second-smooth. For a *simulated-frame* heatmap that's the right
  amount of real-time; if we needed 30 fps continuous animation we'd outgrow it.

---

## 2. Voice stack (both surfaces)

**Decision: Deepgram for STT and TTS on both surfaces; a small LLM (Haiku 4.5, §4) for intent
parsing and broadcast composition. No second TTS provider — Deepgram Aura-2 covers English +
Spanish.**

- **What it does.**
  - *Operator (voice-in):* mic → **Deepgram Nova-3 streaming STT** (WebSocket, sub-300ms) →
    final transcript → small-LLM **structured intent extraction** → dispatch
    `OperatorCommand`. Streaming matters here (hands-free responsiveness).
  - *Subject broadcast (voice-out):* `LocatedEvent` + map state → small-LLM composes a short
    situational message → **Deepgram Aura-2 REST TTS** (voice chosen by language: `…-en` /
    `…-es`) → play through simulated drone audio. Streaming does **not** matter here (short,
    pre-composed) — REST is simpler and robust.
- **Why it fits.** Deepgram is the committed sponsor and is genuinely voice-native for both
  directions. The biggest risk going in — "can Deepgram TTS speak Spanish well?" — resolved
  clearly **yes**: Aura-2 ships 17 Spanish voices (regional accents) plus English↔Spanish
  code-switching voices. So one provider covers the multilingual broadcast (the cheap stretch),
  lower latency and complexity than bolting on a second TTS. Raw API calls in a light async loop
  — no orchestration framework needed. *(Maps to: lightest thing that works; sponsor follows the
  build, not vice versa.)*
- **Simpler alternative considered (intent).** Keyword/regex intent parsing — zero deps,
  deterministic — works for a tiny fixed command set but is brittle on natural phrasing
  ("where's the best spot to look?" won't match "highest-probability area"). **Recommend the
  small-LLM structured-output parser** for the demo's paraphrase-heavy queries, with an optional
  keyword fast-path for 2–3 critical commands ("broadcast now", "abort") as a deterministic
  safety net.
- **Alternative rejected.** A second TTS provider (ElevenLabs/OpenAI/Google) for Spanish —
  unnecessary complexity given Aura-2's Spanish coverage. Only revisit if a language *outside*
  Aura-2's 7 is ever needed.
- **Gotchas to remember (build-time).** STT WebSocket drops after ~10s of no audio (send silence
  frames / keepalive); STT `sample_rate` must match the mic; TTS encoding/sample-rate must match
  the player or audio plays at the wrong speed; keep broadcast messages short (TTS latency grows
  with text length, and short suits SAR clarity). New accounts get $200 free credit — covers the
  weekend.

---

## 3. Detector

**Decision: Ultralytics YOLO11 (`yolo11s.pt` → `yolo11m.pt` if needed), person-only
(`classes=[0]`), wrapped in SAHI sliced inference, behind a thin swappable `Detector` Protocol.
For the thermal story, run a downloaded thermal-fine-tuned checkpoint on WiSARD thermal frames.**

- **What it does.** YOLO11 is the current Ultralytics detector; COCO weights auto-download and
  already include a `person` class, so the loop has a working detector immediately. **SAHI**
  (Slicing Aided Hyper Inference) tiles each large aerial frame into overlapping patches, runs
  the detector per patch so a tiny person occupies far more pixels, and merges detections back.
- **Why it fits.** Proven-stable, fastest path to a working loop, identical API for later
  swaps. SAHI is the single highest-leverage no-training move for this imagery: HERIDAL persons
  are ~0.03–0.1% of a 4000×3000 frame (right at the detection floor even at high `imgsz`), and
  sliced inference buys ~+5–7 AP with no retraining — and caps peak GPU memory, solving the
  "can't feed a huge frame whole" problem for free. The `Detector` Protocol (a Strategy pattern —
  any class with a `detect()` method satisfies it) keeps the backend swappable per
  `interfaces.md` §0, so YOLO11 → a fine-tuned `.pt` → a thermal `.pt` is a one-line construction
  change. *(Maps to: swappable component invariant; cap time chasing accuracy.)*
- **Manage expectations (important).** Off-the-shelf COCO detectors score *single-digit AP* on
  tiny-aerial-person imagery (documented ~5.9% AP), because COCO is ground-level and frame-filling
  while SAR is top-down and tiny. **This is expected and acceptable** — the loop working
  end-to-end is the weekend goal; accuracy is the (optional, well-understood) fine-tuning stretch
  that reaches ~84–86% AP on HERIDAL. Don't chase it on the core path.
- **Thermal (the canopy/low-light story).** Don't fight the RGB→thermal domain gap zero-shot.
  Cheapest thing that demos well: download a thermal-fine-tuned checkpoint and run it on WiSARD
  thermal frames; for the money-shot, on the *same synchronized WiSARD pair* show stock RGB
  *missing* the person and thermal *catching* them in a night/under-canopy scene. (WiSARD's own
  baseline: thermal beats RGB on recall 0.96 vs 0.85 under canopy.) Honest caveat to voice:
  thermal's edge is strongest at night/low-light; it can't see through solid trunks.
- **Licensing caveat — decide early.** The `ultralytics` package and its weights are **AGPL-3.0**
  (network copyleft). For a **local/internal demo this is dormant** (no public network-served
  users → no trigger). It only bites if we host it publicly or ship closed-source — at which
  point: open-source the app, buy the Ultralytics Enterprise License, or switch to an Apache-2.0
  detector (Baidu RT-DETR / D-FINE). The swappable `Detector` seam keeps that switch a one-liner.
- **Alternatives considered.** YOLO26 (newer, NMS-free, faster) — adopt as a later drop-in once
  the loop is solid; not the first pass. RT-DETR (transformer, stronger on small/cluttered) —
  the **fallback** if YOLO small-object recall stalls; the Apache-licensed Baidu repo also dodges
  AGPL. Raising `imgsz` instead of SAHI — helps but still downsamples the whole scene; SAHI feeds
  each region through the full input window, which is what tiny persons need.

---

## 4. The LLM (broadcast composition + intent parsing)

**Decision: Claude Haiku 4.5 (`claude-haiku-4-5`) for both. Upgrade to Sonnet 4.6
(`claude-sonnet-4-6`) only if message nuance or intent accuracy demands it.**

- **What it does.** Composes the short subject-broadcast message from structured state
  (location-relative guidance, stay-put, help-status; target-language variant), and parses
  operator speech into a structured `{intent, params}` via structured outputs.
- **Why this capability level.** Both tasks are short, well-scoped generation/extraction — the
  textbook case for the lightest, cheapest model. Haiku 4.5: 200K context, **$1 / $5 per MTok**
  (input/output), fast. The broadcast is a few sentences; intent parsing is a constrained schema
  fill — neither needs Opus/Sonnet-tier reasoning. *(Maps directly to: "use the lightest model
  adequate for the task.")*
- **Upgrade path.** If multilingual phrasing or empathetic tone needs more polish, or intent
  extraction misclassifies paraphrases, step up to **Sonnet 4.6** ($3 / $15) — still well below
  Opus. Don't default to the bigger model; measure first.
- **Build note.** Use the Anthropic SDK with structured outputs (`output_config.format`) for the
  intent schema and a simple call for the broadcast text. Keep the API key in the gitignored
  `.env`. This is the Anthropic sponsor surface (composing voice content); the agentic coding
  tool is the other Anthropic story.

---

## 5. Summary table

| Track | Pick | Fallback / upgrade | Key reason |
|-------|------|--------------------|-----------|
| Dashboard | Streamlit + image-overlay map (`st_folium`), fragment refresh | Plotly/Matplotlib heatmap (same shell) | Pure-Python, low frontend cost, "live enough" at a few fps |
| STT | Deepgram Nova-3 streaming | — | Sponsor, voice-native, low-latency hands-free |
| TTS | Deepgram Aura-2 REST (en + es voices) | — | One provider covers EN+ES; no second TTS needed |
| Intent | Small-LLM structured output (+ keyword fast-path) | Keyword/regex only | Handles paraphrase; schema removes fragile parsing |
| Detector | YOLO11s/m + SAHI, `classes=[0]`, behind `Detector` Protocol | RT-DETR (recall) / YOLO26 (newer); thermal `.pt` for WiSARD | Fastest working loop; SAHI is the no-train small-object lever |
| LLM | Claude Haiku 4.5 (`claude-haiku-4-5`) | Sonnet 4.6 if nuance needed | Lightest model adequate for short generation/extraction |

> Detector weights and their provenance/licensing live in `data/README.md` → `weights/`.
> The AGPL caveat (Ultralytics) is the one licensing item to resolve before any public hosting.
