# How We Build This in 24 Hours — Plan & Feasibility

*For the three of us — to decide together whether this is doable with 3 people, and to guide the
build. Read the verdict first; the rest is the how. This doc stands on its own.*

**The project in one paragraph.** We're building the **decision brain behind a search-and-rescue
drone** — not the drone. The core is a **probability map** of where a missing person likely is: it
directs where to search, the drone's detections (and clean *non*-detections) update it, and the
updated map redirects the next search. When a detection is confident and persistent, the system
speaks a message to the subject and alerts the operator. We build and demo it **in software**, over
recorded aerial footage and a scripted flight path — no real drone required. The probability map is
the center of gravity, because it's the part that visibly *reasons* about where to look.

---

## 1. Feasibility verdict — can 3 people do this in ~24h?

**Yes — a real, closing loop is achievable in 24h with 3 people, *if* we hold a few disciplines.**
Each individual piece is a few hours of mostly off-the-shelf work. The hard, make-or-break part is
making them form **one loop that actually closes** — a detection visibly moves the map and triggers
the broadcast — instead of three polished but disconnected features.

**What makes it work:**
- **Ratify the contracts in the first hour**, then build against stubs so all three of us
  parallelize without waiting on each other.
- **The brain gets our strongest owner from minute one** — it's the critical path and the novel core.
- **Integrate continuously and early**, not at hour 20.
- **Cut ruthlessly** down the stretch list; protect the loop.

**Why our odds are better than they might look (the key framing):**
- Our integration is **software-only, in-process, single-writer, and deterministic over recorded
  footage**. No live drone, no real-time control, no multi-process hardware bridge — we can replay
  the same footage + scripted flight as many times as we want.
- That matters because the closest comparable project (SkySearch — same ~24h, but *four* people; see
  §8) did **not** close its loop, and a large part of *why* was that they were fighting a **live-drone
  real-time bridge**. We deliberately removed that variable: hardware (the Coral board) is a
  secondary, off-critical-path option, **not** part of the loop.
- So the residual risk sits on our **novel algorithmic core — the probability map (brain) and the
  georeferencing** — not on an integration or hardware bogeyman. That's a more tractable place to
  carry risk, and it's where our strongest person should be.

**The honest flip side:** if the brain or the georeferencing doesn't land in time, we fall back to
demoing the loop on a **scripted map sequence** (Tier B, §3) — still shows the reasoning, but labeled
honestly. The whole plan exists to land the real thing (Tier A).

---

## 2. What we CAN and CANNOT do

**The must-hit core (this is the win):**
prior map → directs the search → detector finds a person in footage → georeference + map update →
updated map redirects + a confident, persistent detection → spoken broadcast + operator alert —
running on recorded footage + a scripted flight over a real region, with the map visibly updating
live.

**Stretch — taken only once the core is solid (drop in this order, last-in-first-out):**
1. Operator voice interface (hands-free query/command) — *first to cut*
2. Multilingual broadcast (nearly free — the message is generated)
3. Detector fine-tuning (a swappable accuracy upgrade)
4. The Coral on-device exhibit (isolated, off the critical path)

**Out of scope (not this weekend):** a real flying drone; autonomous flight/navigation; live thermal
hardware; radio/phone detection. *(Thermal imagery via datasets is fine; live thermal hardware is
not.)*

**The fallback ladder (so we never fake the demo without knowing it):**
- **Tier A (aim here):** the real loop closes on recorded footage + scripted flight.
- **Tier B (fallback):** if the brain/geo slips, the loop runs on a **scripted map-state sequence** —
  honestly labeled "simulated." Still shows the reasoning; we just don't claim it's live.

---

## 3. The parts (what makes up the project)

| Part | What it does | Effort (1 owner) | Risk |
|------|--------------|------------------|------|
| **Prior-data ingestion** | Turns gathered terrain layers (elevation, land cover, trails) into the starting probability map over the region. | 3–5 h | med |
| **Detector** | Runs a pretrained person detector (YOLO11 + **SAHI** tiling for small aerial people) on recorded footage; outputs boxes + confidence, pixel-space only, swappable backend. | 3–5 h | med |
| **GeoReferencer** | Ties each video frame to the patch of ground it covered, so a detection lands on the right map cells (and a non-detection clears the right cells). Custom geometry, no off-the-shelf shortcut. | 4–6 h | **med-high** |
| **The Brain** | Holds the map; applies the Bayesian update each frame (a detection sharpens it, a clean non-detection clears the searched area); decides where to look next; fires the "located" trigger after a detection persists. **Critical path + novel core**; the only writer of shared state. | 6–10 h | **highest** |
| **Dashboard** | A simple live view (Streamlit) of the map state: probability heat, where we've looked, detections, search path, "located" alert. Reads state, never writes. | 2–4 h | low |
| **Subject broadcast** | On a confident find, composes a short situation-aware message ("stay put, help is coming") with an LLM and speaks it via TTS; multilingual nearly free. **Protected — the demo's high point.** | 2–3 h | low |
| **Operator voice** *(stretch)* | Hands-free: speech → intent → a command into the system; spoken answers to queries. First to cut. | 3–4 h | med |
| **Integration / loop wiring** | The connective tissue that makes the above **one loop**: detector → georeferencer → brain → dashboard/broadcast. Called out as its own part **because it's where the comparable project died** — but for us it's software-only and in-process, so it's tractable *if done continuously, not at the end.* | continuous | high if back-loaded |

---

## 4. How we split it across the three of us

Three role-clusters, grouped so each person owns a coherent slice and the contracts keep us from
colliding:

**Cluster A — Surfaces (Dashboard + Voice).** The dashboard (Streamlit map view) + the subject
broadcast (+ operator voice if we get there). All of it *reads* the map state and talks to external
voice APIs — it's UI + API integration, and it can start immediately against a mock map.
→ **Recommended owner: the full-stack teammate** — this plays directly to front-end + back-end
strength.

**Cluster B — The Brain + integration lead (critical path).** The probability map, the Bayesian
update, the "located" trigger, and leading the loop wiring (the brain is the convergence point — the
only writer of shared state).
→ **This is the single most important assignment. Give it to whoever among us is strongest on
probability / search-theory / Python, and decide it consciously, not by default.** (Whoever has the
math/ML comfort is the natural fit.)

**Cluster C — Perception → ground (Detector + GeoReferencer + prior-data ingestion).** Get real
detections out of footage and onto the map: the detector (mostly off-the-shelf), the georeferencer
(the pixel→ground geometry), and the terrain-data ingestion that builds the prior. The "input side"
of the loop.

**On the unknown third skill set.** Since we don't yet know one teammate's strengths, the safe
default is to give the least-known person the **most contract-guarded, most off-the-shelf-heavy**
work, paired with Claude Code: the **detector** (YOLO+SAHI is well-trodden) or the **dashboard** are
the most "followable" slices. **Keep the brain with a known-strong owner** — it's the one place we
can't afford a slow start. We re-sort after the first hour once we see what everyone's comfortable
with; the contracts make swapping cheap.

**Why this parallelizes cleanly.** Once the contracts are fixed (hour 1), each cluster builds against
**stubs** of its inputs — the dashboard against a mock map, the brain against mock observations,
perception against recorded frames — so nobody blocks anybody. The only hard dependency is that the
brain must land for the *real* loop (versus the Tier-B scripted fallback).

---

## 5. The 24-hour sequence

Phases with checkpoints. The point of the ordering is to **integrate early** — the comparable
project failed by leaving integration to the final hours. The checkpoints are **decision gates**:
missing one triggers a cut, not a crunch.

- **P0 — Setup (hour 0–1, together).** Ratify the contracts (what the detector outputs, what the map
  consumes, what the voice/dashboard read). Scaffold the repo + the shared types. Set up `.env` with
  the API keys. Agree the role split. *Then everyone starts.*
- **P1 — Build against stubs (≈1–8h, parallel).** Brain: prior + update loop on **mock observations**
  so the map moves. Perception: detector emitting real detections on recorded frames + the
  georeferencer turning them into map updates. Surfaces: dashboard rendering a **mock map**, broadcast
  speaking from a **mock "located" event**. *Gate (~h6–8): each piece runs on stubs — the map moves,
  the detector fires, the dashboard renders.*
- **P2 — First real integration (≈8–14h). The make-or-break.** Wire detector → georeferencer → brain
  → dashboard on **real recorded footage + the scripted flight path**. *Gate (~h14): a real detection
  visibly moves the real map on the dashboard.* If we're not here by ~h14, make the call: fall back
  to Tier B (scripted map) and cut stretches.
- **P3 — Close the loop (≈14–19h).** Wire the "located" trigger → the broadcast; tune the knobs
  (detection thresholds, persistence, prior weights) live; lock the demo path (region, scripted
  flight, footage). *Gate (~h19): the full demo runs end-to-end (Tier A).*
- **P4 — Stretch or harden (≈19–22h).** Only if the core is solid: take stretches in cut-line order
  (operator voice → multilingual → fine-tune → Coral). Otherwise: harden the core and rehearse.
- **P5 — Freeze & submit (final ~2h).** Stop adding features. Rehearse the demo until it's reliable.
  Finalize and submit the Devpost entry — most of the write-up is already drafted from our project
  docs, and Devpost usually unlocks late, so this naturally lands here.

---

## 6. Risks & how we de-risk them

Ordered by where the real risk is:

1. **The brain / georeferencing not landing (the dominant risk).** The novel algorithmic core — no
   off-the-shelf shortcut, and no prior-project proof it's 24h-sized. *De-risk:* strongest owner from
   minute 1; build it against **mock observations** first (working before real data arrives); keep
   the Tier-B scripted-map fallback ready so the demo survives even if the live update isn't perfect.
2. **Aerial person detection being weak.** Our own Coral testing showed people are genuinely hard to
   detect in full aerial frames. *De-risk:* SAHI tiling, person-only, and **pick favorable demo
   footage**; cap the time — a passable detector feeding a great map beats the reverse. Don't
   rabbit-hole on accuracy.
3. **Integration crunch.** Real, but **lower for us than it looks**: our loop is software-only and
   in-process (no live drone), and we front-load it (P2) behind a gate. *De-risk:* continuous
   integration against stubs from P1; the ~h14 gate.
4. **The unknown third skill set.** *De-risk:* give that person the most contract-guarded /
   off-the-shelf slice, pair with Claude Code, re-sort after hour 1; never put the brain on an
   unknown.
5. **Scope creep / four-disconnected-features.** *De-risk:* the cut-line, the gates, and a hard
   feature freeze at P5.

---

## 7. What the comparable project (SkySearch) teaches us

SkySearch (CalHacks, the same ~24-hour window, a **four**-person team) is the closest prior art.
What actually happened, and what we take from it:

- They built **more** components than we plan — working detection, an overnight fine-tune, a polished
  mission-control web app with hazard-avoidance routing, even 3D reconstruction — and yet **the loop
  never actually closed**: the live "detect → map → decide" path was largely **hardcoded simulation
  data**, and the real integration was crammed into the final quarter.
- **Most of their time went to UI polish**, and they **sidestepped the hard detection problem** —
  their footage was low-altitude with large subjects, so they never faced tiny-aerial-person
  detection.
- **Crucial caveat — don't over-learn from their failure:** a large share of their integration pain
  was **hardware-coupled** — a live drone + a real-time control bridge that was broken by design.
  **We don't carry that.** Our hardware is a secondary, off-critical-path option, so our loop is
  software-only and in-process — meaningfully more closeable than theirs was.

**Takeaways:** protect the loop above all; integrate early; keep the UI minimal; remember components
≠ a working system — *and* that removing the hardware variable puts the loop genuinely within reach,
so our worry belongs on the brain/geo algorithm, not on the wiring.

---

## 8. The cut-line & decision gates (at a glance)

**Cut order under time pressure (drop from the top, never into the core loop):**
Coral exhibit → detector fine-tuning → multilingual broadcast → operator voice.

**Decision gates:**
- **~h14:** real detection moves the real map? **No → switch to Tier-B scripted map, cut all stretches.**
- **~h19:** full demo runs end-to-end? **No → freeze scope, make the current state demo-reliable.**
- **P5:** hard feature freeze — rehearse and submit only.

**Bottom line.** With contracts fixed in hour 1, the brain on our strongest owner, the full-stack
teammate on the surfaces, continuous integration, and ruthless cutting, **3 people can close this
loop in 24 hours.** The thing most likely to stop us is the brain/geo algorithm, not the wiring — so
that's where our best effort goes, and that's the part to watch.
