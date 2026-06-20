# Tech Stack & Sponsor Fit

*What we're building with, and which sponsor tech is actually worth using — for the UC Berkeley AI
Hackathon 2026. Standalone reference. Guiding rule: **sponsors follow the build, not vice versa** —
cap integrations so they never eat the core loop.*

---

## Part 1 — Our tech stack (the picks)

Lightest things that close the loop; Python throughout, raw API calls in a light loop (no heavy agent
framework).

| Layer | Pick | One-line why |
|------|------|--------------|
| **Build tool** | **Claude Code** (Anthropic) | Each person drives it on their own component — parallelism + the Anthropic story |
| **Detector** | **Ultralytics YOLO11** (`yolo11s`) + **SAHI** sliced inference, person-only (`classes=[0]`), behind a swappable `Detector` seam | Fastest working loop; SAHI is the no-train lever for tiny aerial people. Thermal = a downloaded thermal `.pt` on WiSARD frames |
| **GeoReferencer** | Custom Python geometry over a shared `GridSpec` | Frame→ground projection; the one place geography lives |
| **Brain** | NumPy probability grid + Bayesian update, **in-process single-writer** `MapState` | The reasoning core; in-process keeps integration deterministic |
| **Dashboard** | **Streamlit** + image-overlay map (`st_folium`), fragment refresh. Fallback: Plotly/Matplotlib heatmap in the same shell | Pure-Python, low frontend cost, "live enough" at a few fps |
| **Voice — STT** | **Deepgram Nova-3** streaming (operator interface) | Sponsor; voice-native, sub-300 ms, hands-free |
| **Voice — TTS** | **Deepgram Aura-2** REST, en + es voices (subject broadcast) | One provider covers EN+ES; no second TTS needed |
| **LLM** | **Claude Haiku 4.5** (`claude-haiku-4-5`) — broadcast composition + operator intent parsing; Sonnet 4.6 only if nuance demands | Lightest model adequate for short generation/extraction |
| **State store** | In-process (serializable) | Redis only if we genuinely go multi-process — see Part 2 |

*(Deeper justifications, fallbacks, and the Ultralytics AGPL caveat are in `docs/tech_stack.md`; this
table is the at-a-glance version.)*

---

## Part 2 — Sponsor fit (what's usable for *our* project)

The event's sponsors mapped to our build. Tiered by how much they actually fit the SAR system —
**committed → near-free → conditional → skip**. We only adopt what the build wants; the prize is a
bonus, never the driver.

### Tier 1 — Committed (already core to the build)
| Sponsor | What they offer | How we use it | Prize |
|---|---|---|---|
| **Anthropic** | Claude Code; Claude API | **Our build tool** + Haiku for the broadcast message + operator intent. Their track rewards Claude Code projects for **"health, education, economic opportunity"** — finding missing people is squarely social-impact/safety. | $5,000 API credits (total), Applied-AI office hour, SF office visit |
| **Deepgram** | "speech-to-text, text-to-speech, or the voice agent API" | **Both voice surfaces** — Nova-3 STT (operator) + Aura-2 TTS (broadcast). (Their *voice agent API* could power the operator interface more directly if we want.) | **Nintendo Switch 2 per team member** |

### Tier 2 — Near-free, worth claiming
| Sponsor | What they offer | How we use it | Prize |
|---|---|---|---|
| **Sentry** | Error monitoring / observability | Wrap the pipeline in Sentry error capture (~30 min). The **reliability narrative fits a safety-critical SAR system** well, and it's near-free. | **Nintendo Switch 2 per team member** |

> Note: Deepgram + Sentry each give a **Switch 2 per member** and are both low-effort / already-planned
> — the highest reward-to-effort sponsors on the board.

### Tier 3 — Conditional / optional (only if the build genuinely wants it)
| Sponsor | What they offer | Fit — adopt only if… | Prize |
|---|---|---|---|
| **Redis** | Vector sets + vector search / RedisVL (Redis 8), Streams & Pub/Sub, RedisJSON, LangCache semantic caching | **The strongest-fitting conditional** — as the **shared read-model + event hub** between the brain and the consumer surfaces (dashboard + voice), which run as separate processes. A genuine architectural fit, not prize-chasing. **See the expanded note below.** | 25k Redis Cloud credits, Mac Minis |
| **Ultimate Bots** | Physical-AI/robotics + **Nebius Physical AI Workbench ($150 compute/team)** | …we frame our **scripted flight path as a simulated drone** in the loop (it nearly is). The $150 Nebius compute is a tangible perk (could host SAHI / a fine-tune). | $3,000 + SF show |
| **Arize** | Observability/eval — **Phoenix** (open-source LLM tracing) + **AX** (model monitoring) | **Watches the system; never load-bearing** (the key contrast with Redis). The *wiring* is cheap, but the criterion — "Arize *actually improved* the app" — demands an observe→change→measure cycle on a model, and our detector is deliberately frozen + the LLM usage is trivial. Genuine only if **gated behind the fine-tuning stretch (#3)** with real slack — a stretch on top of a stretch. | $1k (gift cards) |
| **QNX** | Embedded OS + open-source AI modules | …we commit to the **physical/on-device** angle (our Coral stretch). Hard reqs: "uses QNX OS" + an `oss.qnx.com` module — heavy OS integration for 24h. **At most one physical angle (Coral *or* QNX).** Likely skip. | $1,000 + 2×$250 |

#### Redis — the concrete use case (why it fits, not forced)

Our resolved design (`interfaces.md` / `CLAUDE.md`) is **in-process single-writer `MapState`, kept
serializable so it can cross a process boundary** — explicitly: "Redis only if we actually go
multi-process; don't add it for the prize alone." We almost certainly **are** multi-process: the
pipeline (detector → geo → brain) is one process, but the **Streamlit dashboard and the voice surfaces
are separate processes** (a different owner — the Surfaces cluster). They must read the live
`MapState` / `LocatedEvent` the brain produces, and that hand-off needs *some* transport. Redis is the
clean, idiomatic one — and it lands exactly on the seam we pre-built.

**The fit (single-writer invariant preserved):**
- **Latest state** → the brain writes serialized `MapState` to one Redis key per update (RedisJSON or a
  blob; the ~160×160 posterior is ~200 KB). `MapState.update_count` lets readers detect new state
  cheaply. **Only the brain writes that key**; dashboard + voice read — Redis is just the transport, the
  single-writer rule is unchanged.
- **Events** → `LocatedEvent` + the detection log on a **Redis Stream** (survives reconnects, feeds the
  dashboard timeline; the broadcast subscribes and fires).
- **Operator → system** → `OperatorCommand` back to the brain via a Stream/list, preserving "voice never
  mutates `MapState` directly."

**Effort/risk: low.** A local `redis-server` (or `docker run redis`) + `redis-py` + a ~30–60-line
put/get wrapper in `src/common`. It **replaces** a hand-rolled cross-process mechanism rather than
adding net scope; the fallback is file-based sharing. **Decide it at the P2 integration phase** (when
wiring the dashboard to real `MapState`) — until then keep `MapState` serializable so it stays a
drop-in.

**Optional stretch (only if the core is solid):** RAG over SAR knowledge via **RedisVL vector search** —
retrieve Koester / lost-person-behavior stats or SAR-protocol snippets to ground the broadcast message
(or shape the prior). Leans into Redis's headline feature, but adds scope; the prior is already numeric
and the broadcast is short, so it's polish, not core.

**Skip:** LangCache semantic caching of LLM responses (too few calls; latency isn't the bottleneck) and
"agent memory" (we're a pipeline, not an agent loop) — both would be forced.

**Verdict:** adopt Redis as the **shared read-model + event hub** *if* the dashboard/voice run as
separate processes (the likely reality) — genuine architectural use, low-risk, with the prize as a
bonus. Don't adopt it if the build collapses to a single process.

### Tier 4 — Skip / no fit (don't force the architecture)
- **Fetch AI** (co-host) — agent platform (Agentverse, ASI:One, Chat/Payment Protocol). Our loop is a
  single-writer pipeline, not an agent mesh. *Cautionary note: SkySearch used Fetch.ai uAgents for its
  drone agent — and that bridge is exactly what broke. Don't force it.*
- **Band** — requires "≥2 agents collaborating via BAND." We're not multi-agent; don't bolt one on.
- **Orkes (Agentspan)** — agent orchestration; our loop isn't orchestration-shaped.
- **Browserbase** — web automation (browsers/search/fetch/Stagehand). No fit.
- **Cognition (Devin)** — alternative coding assistant; we use Claude Code. Don't split build tools.
- **Terac** — annotation platform; requires "training data must come from annotations collected through
  Terac during the event." Conflicts with our pre-gathered datasets; only relevant if we fine-tune on
  Terac-labeled data (a dependency we don't need in 24h).
- **Pika / Midjourney** — video / image generation. No fit for the project itself — *Pika could help
  produce the submission video* (tangential, optional, end-of-event).
- **Simular, Cognichip, Interaction Co, The Token Company, Annapurna Labs, PaleBlueDot, Overshoot,
  Fieldguide** — no fit, out of scope, or "coming soon."

---

## Part 3 — The integration budget (the rule)

- **Committed:** Anthropic + Deepgram (already in the stack, zero extra cost — they *are* the build).
- **Near-free add:** Sentry (reliability story + a Switch 2 per member for ~30 min).
- **Everything else** only if it falls out of the build for free, or the core genuinely needs it
  (Redis for RAG/multi-process; Ultimate Bots if we lean into the simulated-drone framing).
- **Cap sponsor integrations** so they never draw time from the loop. A clean core loop with one
  strong voice moment beats a wide, shallow spread of sponsor logos.

*Relationship to other docs: this enriches the prize strategy in `SAR_project_plan.md` §12 with the
sponsors' actual current offerings/requirements; the deeper stack rationale is in `tech_stack.md`.*
