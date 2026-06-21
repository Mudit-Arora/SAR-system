# =============================================================================
# integration/server.py
# -----------------------------------------------------------------------------
# Responsible for: Serving the live HYBRID dashboard map + panels over HTTP. The server
#                  pre-computes the 3-drone search + guide-home run, renders the unified BASE
#                  image per frame (terrain + posterior + sectors), and publishes the per-frame
#                  vector + panel state. The browser composites: base image (GET /map_base.png)
#                  under live vector overlays (GET /state).
# Role in project: The transport seam. One stepper thread advances the frame index (the single
#                  writer); HTTP handlers only READ cached state/bytes under locks. The base
#                  image and the vectors are keyed to the same `frame` index so they never drift.
# Run: .venv/bin/uvicorn integration.server:app
#      (env: SAR_STEP_INTERVAL = seconds per frame, default 0.7)
# =============================================================================

from __future__ import annotations

import math
import os
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from src.common.contracts import CameraPose, Cell, LocatedEvent, Status
from src.demo.search_demo import _DRONE_COLORS
from src.demo.search_and_guide import _guiding_drone_id, run_combined
from integration.broadcast import _location_phrase, compose_broadcast
from integration.dashboard_projection import DroneVector, ProjectionContext, project
from integration.deepgram_tts import deepgram_api_key, synthesize
from integration.map_render import base_hillshade, render_base_frame
from integration.observability import init_sentry
from integration.terrain_render import render_terrain_png

# Languages we can voice with a Deepgram Aura model. English is mapped; other languages (e.g.
# Spanish) fall back to the browser's TTS in the dashboard (Aura is English-first). Adding a
# Deepgram Spanish voice here later is a one-line change.
_LANG_VOICE = {"en": "aura-2-thalia-en"}

# Seconds between frames — the demo cadence. A display tunable, not part of the math.
_STEP_INTERVAL_S = float(os.environ.get("SAR_STEP_INTERVAL", "0.7"))

# Fleet size for the dashboard scenario (the 3-drone coordination showcase).
_N_DRONES = 3

# Human landmark anchoring the AOI, for spoken answers from the operator voice agent.
# The demo region is fixed (Marin / Mt. Tamalpais) and the search is seeded at the
# last-known position at the Pantoll trailhead, so naming it is truthful for this build.
# It lets /ops report locations as a landmark ("near the Pantoll trailhead") instead of
# raw coordinates the agent would otherwise read aloud.
_AOI_LANDMARK = "the Pantoll trailhead"

# The guidance sim emits hundreds of fine ticks; replay this many so the guide-home phase
# plays out in a watchable time (a display cadence, not a sim change).
_GUIDE_FRAMES = 36

# Seconds of sim time per frame, for the trend chart's x-axis (a monotonic display clock).
_FRAME_DT_S = 9.0

# Allowed browser origins (the Vite dev server) — CORS for the cross-origin :5173 -> :8000 fetch.
_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _located_to_dict(event: LocatedEvent) -> Dict[str, Any]:
    """
    Serialize a LocatedEvent for the /located endpoint.

    Args:
        event: The brain's LocatedEvent.

    Returns:
        A JSON-serializable dict (tuples flattened to lists).

    Why:
        The broadcast/voice surfaces consume the event over HTTP, so we flatten the dataclass
        here rather than leaking its tuple fields.
    """
    return {
        "cell": list(event.cell),
        "latlon": list(event.latlon),
        "confidence": event.confidence,
        "terrain_context": event.terrain_context,
        "timestamp": event.timestamp,
    }


class LoopRunner:
    """
    Pre-computes the 3-drone run, streams its base frames + vector/panel state by frame index.

    Why:
        The hybrid map needs the demo's unified base image AND live vector overlays, kept in
        lockstep. Pre-computing the whole run (reusing run_combined) makes that trivial: every
        frame's base, vectors, and panels come from ONE recorded run, so they can never disagree.
        One stepper thread advances the index (single writer); requests read cached bytes/state.
    """

    def __init__(self) -> None:
        """Build the run and publish frame 0. Why: /state + /map_base are valid before any step."""
        self._lock = threading.Lock()          # guards the published /state dict
        self._render_lock = threading.Lock()   # serializes matplotlib base rendering (not threadsafe)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state_dict: Dict[str, Any] = {}
        self._located: Optional[Dict[str, Any]] = None
        self._base_cache: Dict[int, bytes] = {}
        self._guide_base: Optional[bytes] = None
        self._terrain_png: Optional[bytes] = None
        self._build()

    # --- build / scenario setup ---

    def _build(self) -> None:
        """
        (Re)compute the 3-drone search + guide-home run and publish frame 0.

        Why:
            Used on construction and /reset, so the demo can replay. Everything the frames need
            (grid, planner, hillshade, the search frames + guidance states) is captured once here.
        """
        combined = run_combined(seed=0, n_drones=_N_DRONES)
        if combined is not None:
            self._result, guidance = combined
        else:
            # Rare: the run didn't locate. Fall back to search-only (no guide phase).
            from src.demo.search_demo import run_multi_drone

            self._result, guidance = run_multi_drone(seed=0, n_drones=_N_DRONES), None

        result = self._result
        self._grid = result.grid
        self._cfg = result.cfg
        self._planner = result.planner
        self._hill = base_hillshade(self._grid)
        self._home_cell: Cell = self._grid.latlon_to_cell(*self._cfg.lkp_latlon)
        self._search_frames = result.frames
        self._n_search = len(self._search_frames)
        self._located_frame = self._search_frames[-1] if self._search_frames else None

        # Guide-home setup (subsampled to a watchable frame count).
        if guidance is not None and result.located_event is not None:
            states = guidance.states
            if len(states) > _GUIDE_FRAMES:
                stride = max(1, len(states) // _GUIDE_FRAMES)
                states = states[::stride]
                if states[-1] is not guidance.states[-1]:
                    states.append(guidance.states[-1])
            self._guide_states = states
            self._guidance_path = guidance.path
            self._guiding_id = _guiding_drone_id(self._located_frame.drones, result.subject)
        else:
            self._guide_states = []
            self._guidance_path = None
            self._guiding_id = 0
        self._guiding_color = _DRONE_COLORS[self._guiding_id % len(_DRONE_COLORS)]
        self._n_guide = len(self._guide_states)
        self._n_total = self._n_search + self._n_guide

        # Reset per-run state and publish frame 0.
        self._i = 0
        self._trend: list = []
        self._base_cache = {}
        self._guide_base = None
        # Not pre-latched: /located stays empty until the PLAYBACK reaches the locate frame
        # (the _advance latch fires when persons_found flips to 1), so the event appears live.
        self._located = None

        # Subject broadcast: compose the spoken message ONCE (the run located); audio is
        # synthesized lazily per language by /broadcast.mp3 and cached. Exposed in /state only
        # from the locate frame onward (like /located), so it appears live, not at t0.
        if result.located_event is not None:
            self._broadcast_texts: Optional[Dict[str, str]] = compose_broadcast(result.located_event)
            self._located_search_index = next(
                (j for j, f in enumerate(self._search_frames) if f.status == "located"), self._n_search - 1
            )
        else:
            self._broadcast_texts = None
            self._located_search_index = self._n_total  # never
        self._audio_langs = list(_LANG_VOICE.keys()) if deepgram_api_key() else []
        self._broadcast_audio: Dict[str, bytes] = {}
        try:
            self._terrain_png = render_terrain_png(self._grid)  # superseded by the base image, kept for /terrain.png
        except FileNotFoundError:
            self._terrain_png = None
        with self._lock:
            self._state_dict = self._project_frame(0)
        self._trend.append((0.0, self._state_dict["confidenceToDeclare"]))

    # --- per-frame state + base rendering ---

    def _synth_pose(self, path: List[Cell]) -> Optional[CameraPose]:
        """
        A plausible CameraPose for the telemetry panel, from the active drone's last step.

        Args:
            path: The active drone's flown cells.

        Returns:
            A CameraPose (heading from the last step, a nominal altitude), or None if no path.

        Why:
            The multi-drone planner loop doesn't surface a single pose per frame, but the
            telemetry readout (altitude/heading/speed) wants one. Synthesizing it from the drone's
            motion keeps the panel alive without threading poses through the recorded run.
        """
        if not path:
            return None
        pos = path[-1]
        prev = path[-2] if len(path) >= 2 else pos
        dr, dc = pos[0] - prev[0], pos[1] - prev[1]
        heading = 90.0 if (dr == 0 and dc == 0) else math.degrees(math.atan2(dc, dr)) % 360.0
        lat, lon = self._grid.cell_to_latlon(*pos)
        return CameraPose(frame_id="live", drone_latlon=(lat, lon), altitude_agl_m=140.0,
                          heading_deg=heading, gimbal_pitch_deg=-88.0, fov_deg=(70.0, 40.0),
                          image_size_px=(1920, 1080))

    def _project_frame(self, i: int) -> Dict[str, Any]:
        """
        Build the /state payload for frame i (search or guide phase).

        Args:
            i: Global frame index (0..n_search-1 = search; n_search..n_total-1 = guide).

        Returns:
            The projected UI-MapState dict for that frame.

        Why:
            One function maps a recorded frame to the dashboard payload — fleet vectors + panels in
            the search phase, the leader + guide overlay in the guide phase — all keyed to `i` so
            the client can fetch the matching base image.
        """
        # The spoken subject broadcast appears from the locate frame onward (else None).
        broadcast = self._broadcast_payload() if i >= self._located_search_index else None

        if i < self._n_search:
            frame = self._search_frames[i]
            map_state = frame.map_state
            drones = [
                DroneVector(
                    id=d.drone_id,
                    color=_DRONE_COLORS[d.drone_id % len(_DRONE_COLORS)],
                    pos=d.path[-1] if d.path else self._home_cell,
                    path=list(d.path),
                )
                for d in frame.drones
            ]
            primary_path = drones[0].path if drones else []
            located = map_state.status is Status.LOCATED
            ctx = ProjectionContext(
                drones=drones, frame=i, home_cell=self._home_cell,
                drone_path=primary_path, last_pose=self._synth_pose(primary_path),
                trend=list(self._trend), started_at="live",
                located_cell=map_state.top_cells[0][0] if located else None,
                guidance_status="searching",
                subject_broadcast=broadcast,
            )
            return project(map_state, ctx)

        # --- guide phase: constant located belief base, the leader + the guide overlay ---
        gi = i - self._n_search
        gs = self._guide_states[gi]
        map_state = self._located_frame.map_state
        leader_path = [s.drone_cell for s in self._guide_states[: gi + 1]]
        leader = DroneVector(id=self._guiding_id, color=self._guiding_color, pos=gs.drone_cell, path=leader_path)
        ctx = ProjectionContext(
            drones=[leader], frame=i, home_cell=self._home_cell,
            drone_path=leader_path, last_pose=self._synth_pose(leader_path),
            trend=list(self._trend), started_at="live",
            located_cell=map_state.top_cells[0][0],
            guidance_path=self._guidance_path, subject_cell=gs.subject_cell,
            guidance_status="arrived" if gi >= self._n_guide - 1 else "guiding",
            subject_broadcast=broadcast,
        )
        return project(map_state, ctx)

    def _base_png(self, i: int) -> bytes:
        """
        The base image bytes for frame i (rendered + cached; the guide base is one constant frame).

        Args:
            i: Global frame index.

        Returns:
            PNG bytes of the unified base for that frame.

        Why:
            Search frames each have their own belief+sectors; the guide phase freezes the belief,
            so its base is rendered ONCE and reused. The render lock serializes matplotlib (which
            isn't threadsafe) across the stepper thread and any request handler.
        """
        if i < self._n_search:
            if i not in self._base_cache:
                frame = self._search_frames[i]
                with self._render_lock:
                    self._base_cache[i] = render_base_frame(
                        self._grid, frame.posterior, self._hill,
                        planner=self._planner, ranked_sectors=frame.ranked_sectors, drones=frame.drones,
                    )
            return self._base_cache[i]
        # Guide phase: one constant base (the located belief, no sectors).
        if self._guide_base is None:
            post = self._located_frame.posterior
            with self._render_lock:
                self._guide_base = render_base_frame(self._grid, post, self._hill)
        return self._guide_base

    # --- the stepper (single writer) ---

    def start(self) -> None:
        """Spawn the background stepper. Why: begins playing the recorded run when the server boots."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sar-frame-stepper", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the stepper to halt and join it. Why: clean shutdown on exit/reset."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        """Advance one frame per interval until the run is finished. Why: the only place state advances."""
        while not self._stop.is_set():
            self._advance()
            self._stop.wait(_STEP_INTERVAL_S)

    def _advance(self) -> None:
        """
        Advance to the next frame: warm its base, project + publish its state, extend the trend.

        Why:
            Pre-rendering the next base in the stepper thread means the request handler almost
            always serves it from cache. Publishing under the lock keeps readers consistent.
        """
        if self._i >= self._n_total - 1:
            return  # at the final frame -> idle (the run is complete)
        self._i += 1
        self._base_png(self._i)  # warm the cache off the request path
        payload = self._project_frame(self._i)
        with self._lock:
            self._state_dict = payload
            # Latch the located event the first frame the brain declares it (persons_found == 1).
            if self._located is None and payload["stats"]["personsFound"] == 1 and self._result.located_event:
                self._located = _located_to_dict(self._result.located_event)
        self._trend.append((self._i * _FRAME_DT_S, payload["confidenceToDeclare"]))

    # --- read model (lock-guarded; called from request handlers) ---

    def state(self) -> Dict[str, Any]:
        """The latest projected UI-MapState. Why: the dashboard's /state poll target."""
        with self._lock:
            return self._state_dict

    def base_png(self, i: Optional[int]) -> bytes:
        """The base image for frame i (or the current frame if None). Why: served by /map_base.png."""
        idx = self._i if i is None else max(0, min(int(i), self._n_total - 1))
        return self._base_png(idx)

    def located(self) -> Optional[Dict[str, Any]]:
        """The latched LocatedEvent dict, or None. Why: drives the broadcast/notify surface."""
        with self._lock:
            return self._located

    def ops(self) -> Dict[str, Any]:
        """
        Voice-friendly SAR facts for the operator telephony agent.

        Returns:
            A dict the agent's sar_service reads over HTTP: {status, located,
            n_drones, elapsed, coverage_pct, coverage_km2, confidence_pct,
            highest_prob{latlon, landmark, description},
            located_info{latlon, terrain, landmark, description} | None}.

        Why:
            A small, speakable projection of the current frame's state — cleaner
            for the agent than parsing the rich UI /state. Read-only: it derives
            from the same single-writer state, surfacing locations as a landmark
            so the agent never reads raw coordinates aloud. Frames are immutable
            after build, so only the live index/state/located read needs the lock.
        """
        with self._lock:
            state = self._state_dict
            located = self._located
            idx = self._i

        # Coverage as a percentage of the whole AOI (the UI exposes only km2).
        cov_km2 = float(state.get("stats", {}).get("areaCoveredKm2", 0.0))
        total_km2 = self._grid.n_rows * self._grid.n_cols * (self._grid.cell_size_m ** 2) / 1e6
        cov_pct = round(100.0 * cov_km2 / total_km2, 1) if total_km2 else 0.0

        # Highest-probability cell of the current frame (clamp into the search
        # frames; during the guide-home phase this reports the located area).
        frame = self._search_frames[min(idx, self._n_search - 1)]
        top_cells = frame.map_state.top_cells
        hp_latlon = None
        if top_cells:
            lat, lon = self._grid.cell_to_latlon(*top_cells[0][0])
            hp_latlon = [round(lat, 6), round(lon, 6)]

        is_located = located is not None
        located_info = None
        if is_located:
            located_info = {
                "latlon": [round(c, 6) for c in located["latlon"]],
                "terrain": _location_phrase(located["terrain_context"], "en"),
                "landmark": _AOI_LANDMARK,
                "description": f"near {_AOI_LANDMARK}",
            }

        return {
            "status": "located" if is_located else "searching",
            "located": is_located,
            "n_drones": _N_DRONES,
            "elapsed": state.get("stats", {}).get("searchTime", "00:00"),
            "coverage_pct": cov_pct,
            "coverage_km2": round(cov_km2, 2),
            "confidence_pct": state.get("confidenceToDeclare", 0),
            "highest_prob": {
                "latlon": hp_latlon,
                "landmark": _AOI_LANDMARK,
                "description": f"near {_AOI_LANDMARK}",
            },
            "located_info": located_info,
        }

    def terrain_png(self) -> Optional[bytes]:
        """The cached colorized terrain PNG (superseded by the base image; kept for /terrain.png)."""
        return self._terrain_png

    def _broadcast_payload(self) -> Optional[Dict[str, Any]]:
        """
        The /state `subjectBroadcast` dict, or None if the run never located.

        Returns:
            {texts: {lang: message}, langs: [...], audioLangs: [langs with Deepgram audio],
             timestamp}. `audioLangs` tells the dashboard which languages to play via
            /broadcast.mp3 (Deepgram) vs. the browser-TTS fallback.

        Why:
            Built from the already-composed message; the dashboard shows the text and decides
            per language whether to fetch Deepgram audio or speak it locally.
        """
        if self._broadcast_texts is None:
            return None
        ts = self._result.located_event.timestamp if self._result.located_event else 0.0
        return {
            "texts": self._broadcast_texts,
            "langs": list(self._broadcast_texts.keys()),
            "audioLangs": self._audio_langs,
            "timestamp": str(int(ts)),
        }

    def broadcast_audio(self, lang: str) -> Optional[bytes]:
        """
        Deepgram-synthesized audio for the broadcast in `lang` (cached), or None.

        Args:
            lang: Language code (e.g. "en").

        Returns:
            MP3 bytes, or None if: not yet located in the playback, no Deepgram key, or the
            language has no mapped Aura voice — in which case the dashboard falls back to browser TTS.

        Why:
            Synthesized lazily on first request and cached per language (one Deepgram call per
            language per run). Gated behind the playback's locate so the audio appears live.
        """
        if self._broadcast_texts is None or self._i < self._located_search_index:
            return None
        voice = _LANG_VOICE.get(lang)
        text = self._broadcast_texts.get(lang)
        if voice is None or text is None:
            return None
        if lang not in self._broadcast_audio:
            audio = synthesize(text, voice=voice)
            if audio is None:
                return None
            self._broadcast_audio[lang] = audio
        return self._broadcast_audio[lang]

    def _status(self) -> str:
        """Current phase: searching / guiding / arrived. Why: /health + tests poll this."""
        if self._i < self._n_search or not self._n_guide:
            return "searching"
        return "arrived" if self._i >= self._n_total - 1 else "guiding"

    def health(self) -> Dict[str, Any]:
        """Run progress for /health and the reset response. Why: lets the UI show frame i/n."""
        return {
            "status": "ok",
            "frame": self._i,
            "n_frames": self._n_total,
            "n_search": self._n_search,
            "done": self._i >= self._n_total - 1,
            "located": self._located is not None,
            "guidance_status": self._status(),
            "n_drones": _N_DRONES,
            "terrain": "REAL rasters (DEM + WorldCover)",
            "step_interval_s": _STEP_INTERVAL_S,
        }

    def reset(self) -> Dict[str, Any]:
        """Stop, recompute, restart. Why: replay the demo without restarting uvicorn."""
        self.stop()
        self._build()
        self.start()
        return self.health()


# Initialize Sentry BEFORE building the runner. LoopRunner.__init__ runs the whole pre-computed
# scenario (_build), and the stepper THREAD advances it later — so initializing here means a crash
# in either is reported. With no SENTRY_DSN this is a no-op, so import stays effectively side-effect
# free (apart from building the run) and the demo is unchanged.
init_sentry("integration-server")

# Module-level runner so `uvicorn integration.server:app` finds a ready `app`. The stepper thread
# is started/stopped by the lifespan handler (not at import), so importing this module is side-effect
# free apart from building the (pre-computed) run.
runner = LoopRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the stepper on startup, stop it on shutdown. Why: ties the thread to the app lifespan."""
    runner.start()
    try:
        yield
    finally:
        runner.stop()


app = FastAPI(title="SAR integration server", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def get_health() -> Dict[str, Any]:
    """Liveness + run progress. Why: a cheap probe the dashboard/ops can poll."""
    return runner.health()


@app.get("/state")
def get_state() -> Dict[str, Any]:
    """The live projected UI-MapState (panels + fleet vectors + frame). Why: the dashboard's poll target."""
    return runner.state()


@app.get("/map_base.png")
def get_map_base(v: Optional[int] = None) -> Response:
    """
    The unified base map image for frame `v` (terrain + posterior + sectors).

    Why:
        The dashboard draws its live vector overlays ON TOP of this. The client passes the `frame`
        it got from /state as `?v=`, so the image and the vectors are the same frame. Each frame's
        image is deterministic and never changes (the run is seeded), so we serve it as immutable
        and cacheable: the `?v=` makes every frame a distinct URL, and immutable caching lets the
        dashboard preload + reuse a frame's bytes instead of re-fetching on each swap — which is
        what makes the map animate smoothly instead of flashing between frames.
    """
    png = runner.base_png(v)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/located")
def get_located() -> Dict[str, Any]:
    """The LocatedEvent once declared, else {"located": false}. Why: the broadcast/notify surface."""
    event = runner.located()
    return event if event is not None else {"located": False}


@app.get("/ops")
def get_ops() -> Dict[str, Any]:
    """Voice-friendly SAR facts for the operator telephony agent. Why: the agent's sar_service reads this."""
    return runner.ops()


@app.get("/terrain.png")
def get_terrain() -> Response:
    """The colorized terrain PNG (superseded by the base image; kept for compatibility). 404 if absent."""
    png = runner.terrain_png()
    if png is None:
        return Response(status_code=404)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/broadcast.mp3")
def get_broadcast(lang: str = "en") -> Response:
    """
    The Deepgram-voiced subject broadcast audio for `lang`, or 404.

    Why:
        The dashboard's "Speak Message" plays this (the sponsor voice) once located; a 404 (no
        key / unsupported language / not yet located) tells the client to fall back to browser TTS.
    """
    audio = runner.broadcast_audio(lang)
    if audio is None:
        return Response(status_code=404)
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.post("/reset")
def post_reset() -> Dict[str, Any]:
    """Replay the run from the start. Why: re-run the live demo without restarting uvicorn."""
    return runner.reset()
