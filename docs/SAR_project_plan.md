# Wide-Area Search and Rescue Support System

**Working title, rename as needed.** Planning document, version 3. This is a living draft for pre-event planning. Nothing here is built code. It exists to lock the architecture, scope, data sources, prize strategy, and execution plan before Saturday so the build hours go to building.

Version 3 records the demo region selection, the detector-to-map architecture seam, and the backend and state decision.

---

## 1. Summary

A drone-mounted system that helps search teams find missing people in remote and complex terrain such as forests and mountains, where low visibility, dense canopy, and difficult ground slow down conventional search. The system is not the drone itself. It is the perception and decision layer that would run on or behind a drone. The core idea is a closed loop: a probability map of where the missing person is likely to be directs the search, the drone's detections update that map, and the updated map directs the next search. A voice layer lets a field operator run the system hands free and lets the system speak to a person once found.

Intended users are organizations that run wide-area searches: park rangers, fire services, police, and other search and rescue teams.

---

## 2. Problem and users

Conventional wide-area search is slow and dangerous. Ground teams cover little area per hour, aerial spotting by eye is fatiguing and misses small or occluded subjects, and there is rarely a principled way to decide where to look next. The hard parts are:

- A person seen from the air covers a tiny fraction of the frame and is often partly hidden.
- Under canopy or in low light, a person is frequently invisible in normal color imagery.
- Search teams need to decide where to allocate limited time, not just scan randomly.
- A located person who keeps moving becomes harder to reach.

The system targets these directly through detection, principled search allocation, and immediate communication with the subject.

---

## 3. System architecture

Four layers. The first three are in scope for the event. The fourth is future work.

### 3.1 Perception layer
Aerial person detection on imagery. A detector runs over drone footage and reports candidate person locations with confidence. The honest constraint is that color imagery fails under canopy and at night, which is why real search and rescue uses thermal. The plan accounts for this by using a dataset that includes thermal pairs so the demo can show both and the team can speak to the limitation when asked. The detector is a swappable component, see section 8.

### 3.2 Search and decision layer (the brain)
A probability map over the search region. A prior is built from terrain difficulty, vegetation density, last known position, and published statistics on how lost people move. The map directs where the drone searches. Each detection, and each clean non-detection of an area, updates the map through a Bayesian step. This is standard search theory and it is the part that turns a detector into a search system. It is also the most compelling thing for a judge to watch, because the map visibly reasons about where to look. This is the project's center of gravity and where it wins.

### 3.3 Communication layer
Two voice surfaces, both genuinely essential rather than decorative.

- **Operator interface.** Voice in. A field operator with busy hands and eyes can query and command the system by speaking. Speech to text plus intent parsing plus system control.
- **Subject broadcast.** Voice out. When the system localizes a probable person, it composes a message from the situation and speaks it through the drone. Content is generated from the detection and map state, for example location relative to the person, instructions to stay put, reassurance, and status on incoming help. Voice is the only channel to a person lost in terrain, since you cannot text or show a screen to someone you have not reached yet. Multilingual output is a natural extension because the message is generated rather than recorded.

### 3.4 Device and signal layer (future, see section 13)
Detecting the subject's phone by its radio emissions and relaying messages to and from it. Real and partly deployed in the field, but blocked from a weekend build by spectrum regulation and radio hardware. Documented in section 13 as a roadmap item that feeds the same brain as a third sensing channel.

---

## 4. The core loop

The thing that has to work end to end:

1. Build a prior probability map of the region.
2. The map directs the drone's search path.
3. The detector runs on incoming footage and reports detections.
4. Detections and non-detections update the map.
5. The updated map directs the next search and flags high-probability areas.
6. On a confident detection, the system composes and broadcasts a voice message to the subject and alerts the operator.

The failure mode to avoid is building separate pieces that do not connect. A working loop where a detection changes the map beats four polished but disconnected features.

---

## 5. Build scope

### In scope for the event (Saturday to Sunday)
- Person detection running on recorded aerial footage, using an existing detector. Light fine-tuning is a stretch item, taken on only if the core loop is solid and time allows.
- The probability map and the Bayesian update loop, run in simulation over a real or synthetic region.
- The wiring that closes the loop, so detections update the map and the map directs search.
- The operator voice interface for hands-free query and command.
- The subject voice broadcast, generated from situation context and spoken through simulated drone output.
- A dashboard showing the live map, detections, search path, and alerts.
- A demo driven by recorded footage and simulated drone telemetry.

### Out of scope, future work (section 13)
- Autonomous flight, navigation, and obstacle avoidance in real terrain.
- Integration with a real flying drone.
- Real-time thermal camera hardware. Thermal imagery is usable in the build through datasets, but live thermal hardware is future.
- On-drone audio source localization, which is defeated by rotor noise.
- Radio detection of the subject's phone and message relay, blocked by spectrum regulation and hardware.
- Field hardening, edge optimization, and full multilingual coverage.

---

## 6. Allowed pre-event preparation

All of the following is parallel work that does not count as building the project. Confirm against the current rules, but planning and data gathering are explicitly fine.

- Download and organize detection datasets.
- Download and organize terrain, elevation, and land cover data for the map prior. Downloading and eyeballing raw data is preparation. The code that ingests, reprojects, and fuses it is building and waits until Saturday.
- Collect recorded aerial search footage for the demo.
- Read published material on lost person behavior to inform the prior.
- Read sponsor documentation and set up accounts and credentials.
- Assign roles across the team.
- Maintain and refine this document and the project agent instructions.

Do not write project code, build models, or assemble pipeline components before the start. Account setup and data collection are preparation. Pipeline code is building.

---

## 7. Datasets and data sources

The detection model has two separate data needs. The first is labeled imagery to fine-tune and evaluate the detector, covered by the datasets below. The second is video to run the detector on as a live feed in the demo, covered under demo feed further down. The detector's confidence score on a frame is the chance-of-a-person reading that updates the probability map.

### Labeled imagery (genuine ML datasets, term used deliberately)
- **HERIDAL.** Around 1650 high-resolution aerial images of non-urban Mediterranean terrain, single person class, very small person instances. The standard aerial search and rescue person detection benchmark.
- **SARD.** Around 1981 labeled images from video of actors simulating tired and injured people across roads, quarries, grassland, and forest in varied weather. Good for transfer learning.
- **WiSARD.** The largest and most useful here. Roughly 33,000 labeled color images and 22,000 labeled thermal images, including around 15,000 synchronized color and thermal pairs, for wilderness search and rescue. This is the dataset that lets the demo show the canopy and low-light limitation honestly and answer the thermal question.
- **SeaDronesSee.** Maritime search and rescue, relevant only if water scenarios are in scope.
- **NOMAD.** Aerial emergency-response data focused on occlusion, relevant if you want to stress the hardest detection cases.

### Terrain and map data (confirmed, free, gatherable by Friday)
- **Elevation.** USGS 3DEP bare-earth DEM through OpenTopography, which lets you draw an area of interest and download a GeoTIFF with a free registration key at 10m and 30m resolution. The National Map Downloader is an alternative direct source. The 1m product is academic-only and not needed.
- **Land cover and vegetation.** ESA WorldCover, a free global 10m land cover layer delivered as GeoTIFF under a permissive license, available as direct download or through Google Earth Engine.
- **Trails, roads, and water.** OpenStreetMap, pulled as a regional extract from Geofabrik or queried through Overpass.

### Lost person behavior
Robert Koester's work on lost person behavior and the associated incident database are the standard basis for probability-of-area models in real search and rescue. Use this to shape the prior rather than inventing movement assumptions. Confidence on this being the standard reference is high. Confidence on specific numbers is low until checked.

### Demo feed and frame-to-ground coverage
Training imagery is still frames, but the demo needs video, or at least a frame sequence, to run the detector on as if it were a live feed. SARD is drawn from video and can serve, and you can source additional openly licensed aerial wilderness footage. If footage with people in it is hard to find, step through dataset images as frames to simulate the feed.

To feed a detection into the map, each frame must be tied to the ground area it covers, so the system knows which map cells to update. In a real drone this comes from GPS plus camera footprint and altitude. In the demo, assign it along a scripted flight path. The same mechanism handles non-detections, where searching an area and seeing nothing should lower its probability, so coverage tracking matters as much as the detections themselves. Keep the detector person-focused for the weekend, since detecting generic objects or clues is harder and the data is thinner.

Note on geography: the detection footage and the chosen terrain region will not share geography, and that is fine for a demo. Do not spend time trying to make the footage and the map the same place.

---

## 8. Technology candidates

Working assumptions below. The resolved picks are a Streamlit dashboard; the Deepgram voice stack for speech-to-text and text-to-speech; a YOLO-family detector with SAHI sliced inference for small aerial persons; and a light LLM for composing the broadcast and parsing operator intent. The map prior is built as described in sections 3.2 and 7.

- Detection: a current YOLO family detector. The detector is a swappable component. The pipeline runs on pretrained weights first so the loop works end to end immediately, and fine-tuned weights drop in if and when the fine-tuning track produces them. See section 10 and section 11.
- Map and search: a gridded probability map with a Bayesian update step, rendered in an interactive map view.
- Voice: a speech provider for both speech to text on the operator side and text to speech on the subject side, with an LLM composing the broadcast content.
- Build acceleration: an agentic coding tool driven by each team member on their own component, so work runs in parallel and the Anthropic story is clean.
- Pipeline and state (resolved). The pipeline is a three-stage seam: detector, geo-referencer, search map, feeding the dashboard and voice surfaces. The detector stays pixel-space and geography-blind so it remains swappable; a dedicated geo-referencing step ties each frame to the ground cells it covers. The map state is a single-writer read model held in process for the baseline and kept serializable so it can cross a process boundary later without a contract change. Redis is added only if a multi-process state layer is genuinely needed, not for the prize alone, see section 12.

---

## 9. Demo plan

What the judges should see, in order:

1. A region loads with a prior probability map that explains where the search should start and why.
2. The simulated drone searches along a path the map directs.
3. The detector finds a probable person in recorded footage.
4. The map updates live and the high-probability area shifts.
5. The system composes and speaks a message to the subject, ideally in a second language, telling them to stay put and that help is coming.
6. The operator runs a step of this hands free by voice.

The map is the centerpiece because it shows the system thinking. The subject broadcast is the emotional high point. The operator interface is the proof that the whole thing runs in the field.

---

## 10. Decisions (resolved)

These were the open questions from version 1. Resolutions and contingencies below.

- **Main track. Deferred to submission, build track-agnostic.** The project does not change based on the track. The same build is pitched to social impact by leading with the human problem and lives saved, or to science and engineering by leading with the search loop and systems depth. Default is social impact for the story. The physical-hardware decision is the tiebreaker, since going physical strengthens an engineering-track pitch. Decide at submission based on the room and on whether hardware materialized.
- **Demo region. Real regional data, region selected.** The primary region is an expanded Marin area running from Mount Tamalpais across Bolinas Ridge into southern Point Reyes, chosen for terrain variety (dense canopy, open ridge, coast), a recognizable landmark, proximity, and genuinely remote wilderness. The region is treated as configuration rather than code, so it is a data swap, and Henry W. Coe State Park is a backup whose layers can be gathered in advance at no build cost. Pull elevation, land cover, and OSM layers per section 7, target Friday, and write the ingestion code Saturday. The area-of-interest bounds are S 37.85, N 38.10, W −122.85, E −122.58 (lon/lat), about 24 km east to west by 28 km north to south.
- **Detection approach. Pretrained first, fine-tune as a swappable upgrade.** Pretraining from scratch is out. The pipeline runs on an off-the-shelf detector so the loop works immediately, and fine-tuning runs as a separate track whose output drops in if ready. Treat fine-tuning as a stretch item, taken on only once the core loop is solid and time remains, since it can otherwise starve the core. Detection is necessary but not where the project wins, so cap the time spent chasing accuracy.
- **Physical versus software. Software-first baseline, hardware additive and isolated.** The core loop runs fully in software. Any board, whether a booth Raspberry Pi or a Google Coral, is an optional demo layer owned by one person, fed by the same detection service, kept off the critical path, and pursued only if the core loop is on track and the hardware is actually secured. The Coral path here is the **Synaptics Coralboard** (SL2619, Astra platform) — a newer board than the legacy Edge TPU line, shipping current on-device vision and LLM demos out of the box. Its toolchain, model-deployment workflow, and input constraints were **assessed on the hardware Friday 2026-06-19**: it runs **Torq-compiled `.vmfb` via IREE** at **320² input** (confirmed **not** the old int8-TFLite / Edge-TPU chain), both IREE and SyNAP runtimes ship, and the on-device YOLOv8 detector + a 270M function-calling LLM both run. The result reframed the board from "stock aerial detector" to an isolated **feasibility-showcase** (two pillars: perception + on-device action) — kept off the critical path. Coral and QNX are different hardware paths, not the same one, so pursue at most one physical angle. Coral is the more demo-friendly story, QNX is the better-fit prize but with more OS-integration overhead.
- **Voice priority. Subject broadcast first, operator interface second, both as the target.** The broadcast is protected because it is cheap and is the demo's high point. The operator interface is the richer build and the first thing to cut under time pressure.

---

## 11. Work breakdown and parallelization

The highest-leverage move is to spend the first 30 to 60 minutes Saturday, before any code, defining the interfaces between components: what the detector outputs, what the map consumes, and what state the voice layer reads. Once those contracts are fixed, people build against stubs in parallel and integrate cleanly. This is what lets the team multiply itself through the coding tool, since each person can drive it on a separate component without collisions. The opening Saturday session ratifies and adjusts these interfaces rather than designing them from scratch.

**Critical path, wants focused single-owner attention.** The map and search loop plus its wiring to detection. This is both the intellectual core and the convergence point, so it resists wide parallelism and benefits from one strong owner or a tight pair.

**Independent tracks, parallelize well against the agreed interfaces.**
- The fine-tuning attempt, which is GPU-bound and largely fire-and-forget once started.
- The subject broadcast, which is almost fully self-contained.
- The operator speech and intent front end, which can be built against mock commands.
- The dashboard shell, which can be built against mock map and detection data.

**Needs sole dedicated focus, resists parallelism.** The search-loop core logic, the final integration where pieces meet, and any fine-tuning debugging, since a training run cannot be crowded.

**Committed core, must ship for a viable demo.** The closed loop of prior map, search direction, pretrained detection, map update, and next search, together with the subject broadcast, the dashboard, and a demo over recorded footage and a simulated flight path. This set is protected and the loop owner holds it.

**Stretch, in priority order, taken on only once the core is solid and slack remains.**
1. The operator voice interface, the second voice surface.
2. Multilingual subject broadcast. The cheapest item in this set, since the broadcast is already generated, so it can be grabbed even with little slack.
3. Detector fine-tuning, a swappable accuracy upgrade rather than a visible feature.
4. A physical or on-device layer, a booth board or a Coral, kept isolated from the core.

Each stretch item is independent enough to add or drop without breaking the core, so how far down this list you get is governed by how much slack the build leaves, whether that slack comes from extra hands or from the core landing early. There is no separate plan per team size. The same ordering holds at any size, and a larger team simply reaches further down it.

---

## 12. Prize strategy

### Committed
- **Main track: social impact (default, deferred per section 10).** A system that finds missing people for rangers and emergency services is a clean social impact story, and that story is what makes a search and rescue project memorable. The science and engineering track is the alternative if you foreground engineering depth or go physical. One main track only, per the rules.
- **Anthropic.** Strong fit. Build through their coding tool and lean into the ambition framing, since the prize rewards the biggest swing at a meaningful problem. No special engineering beyond using the tool.
- **Deepgram.** Strong fit through both voice surfaces. Two voice functions for two purposes read as voice-native rather than voice-decorated.

### Additional sponsors, assessed honestly
The rule for this section is that the project drives the sponsor choice, not the reverse. Sponsors are worth adding only where they serve the system you would build anyway. Several sponsor criteria were still marked as coming soon in the guide, so confirm on the live site Saturday morning.

**Tier 1, near free or naturally implied, worth claiming**
- **Sentry.** Error monitoring. Low cost to add and a reliability narrative fits a safety-critical search system well. Their judging also weights teamwork and communication, which costs nothing extra.
- **QNX.** Conditional on going physical. Their track wants real-time AI running on target hardware such as a single-board computer for mission-critical uses, which describes search and rescue exactly. The cost is running their operating system on the device, so only pursue this if you commit to the physical build.
- **Ultimate Bots.** Conditional on having a simulated drone. Their physical AI track counts a simulated robot, and a drone is a robot. If the demo includes a simulated drone in the loop, this fits with little extra work.

**Tier 2, genuine fit only if the architecture wants them anyway**
- **Redis.** If the backend needs a fast state and memory layer or vector search, for example retrieval over search and rescue protocols or storing detections and search state, Redis fits. Do not add it only for the prize.
- **Orkes.** Workflow orchestration for the multi-stage pipeline. Fits if you build the pipeline as an orchestrated workflow. Criteria were coming soon, so verify.
- **Arize.** Evaluation and observability of the detector. Fits if you want to show evaluation rigor on the model, at the cost of instrumentation time.
- **Band.** Only if you architect the system as two or more collaborating agents. Do not force a multi-agent design for this.

**Tier 3, skip or would distort the project**
- Interaction Co, Fetch AI, Browserbase, Simular, Cognition, Terac, Midjourney, Cognichip, Fieldguide, Context, The Token Company, Annapurna Labs, PaleBlueDot, Overshoot. Either no fit, or pursuing them would warp the project, or the criteria are unknown. Pika could help produce the submission video, which is tangential to the project itself.

**Recommendation.** Commit to the main track plus Anthropic plus Deepgram. Treat Sentry as a near-free add. Treat QNX and Ultimate Bots as conditional wins that follow naturally from the physical and simulation choices if you make them. Ignore the rest unless they fall out of the build for free. Cap additional integrations so they never eat into the core loop.

---

## 13. Future considerations

### Radio detection and relay to the subject's phone
A way for the system to find and message the subject's phone after locating them. This is a real and partly deployed direction, not a moonshot.

- Drones acting as flying cellular base stations are deployed for disaster connectivity. A research system localizes survivors from their phone signals to within tens of meters in a few minutes with no existing network and no phone modification. A commercial detector drone mimics a base station so phones connect and locates them to within about 20 meters over a wide area.
- A lighter approach detects phones by their WiFi and Bluetooth emissions, including having the drone imitate a known home network so the phone reconnects and can be direction-found.
- The connection problem in a no-coverage area is solved by the drone bringing the network with it. Satellite emergency messaging on modern phones is a complementary path, not a competitor, since it needs sky view and the subject to initiate.

The genuine limits:
- Detection works regardless of the subject's state, because a phone emits on its own. Two-way messaging that asks the subject to respond requires them to be conscious and able. Battery death is the universal time limit.
- The real blocker is regulation, not time. Operating or imitating a cellular base station requires licensed spectrum and is restricted, so the cellular version is partnership-dependent. The WiFi route is more accessible but is degraded by modern device identifier randomization and does not deliver messages to the user as cleanly.

How it fits: radio detection is a third sensing channel into the same probability map, with the advantage of reaching a subject under canopy or in the dark. The relay also extends the communication layer by letting the subject send out where there is otherwise no coverage.

### Other roadmap items
- Autonomous flight and navigation in complex terrain.
- Real drone and thermal hardware integration.
- On-drone acoustic detection with rotor-noise suppression.
- Edge optimization for on-device real-time inference. The Coralboard's feasibility pillars — on-device perception (a two-stage proposal→verify cascade) and on-device voice/text→hardware action — were assessed Friday and are deferred and isolated per the physical-layer stretch (section 11, item 4).
- Full multilingual subject communication.

---

## 14. Risks and scope protection

- The plate is full: detection, the map loop, two voice surfaces, and a coding-tool build, in 24 hours. Protect the core loop above all else.
- Fine-tuning and hardware are stretch items, taken on only once the core is solid and slack remains, and the first things to drop if the core is at risk or time runs short.
- Cap the time spent chasing detection accuracy. A passable detector feeding a great search loop beats a great detector feeding a weak one.
- If time runs short, cut from the edges, not the center. The operator voice interface is the first feature to drop, since the subject broadcast carries the stronger voice story for less work.
- Decide the demo region and the detection approach before Saturday so no build time goes to those choices.
- Keep sponsor integrations capped. A clean core loop with one strong voice moment beats a wide but shallow feature set.
- Define component interfaces in the first hour Saturday so parallel work integrates cleanly.
- Ensure the submission entry is finalized and submitted before the deadline so the project is guaranteed to be judged. Devpost typically unlocks late and the write-up is largely drafted from the docs, so it is an end-of-event task rather than something to front-load.
