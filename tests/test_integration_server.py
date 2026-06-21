# =============================================================================
# tests/test_integration_server.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the hybrid FastAPI server (integration/server.py) serves a valid
#                  UI-MapState + fleet vectors + base map image over HTTP, and that the stepper
#                  drives the pre-computed 3-drone run search -> locate -> guide -> arrived.
# Role in project: Guards the transport seam for the hybrid map. /state must be a complete
#                  UI-MapState with drones[]+frame; /map_base.png must serve the base image keyed
#                  to that frame; /located and the guide phase must complete.
# Assumptions: The server runs the REAL-terrain 3-drone scenario, so it needs the DEM/WorldCover
#              rasters. The whole module is skipped without them — AND the server import is done
#              INSIDE the tests, so collection on a raster-less machine doesn't build the run.
# =============================================================================

from __future__ import annotations

import pathlib
import time

import pytest

from src.search.terrain_raster import _DEFAULT_DEM

# The server builds the real-terrain run at import, so skip the whole module without rasters.
pytestmark = pytest.mark.skipif(
    not pathlib.Path(_DEFAULT_DEM).exists(), reason="real DEM raster not present in data/terrain/"
)

# Required top-level keys the dashboard's types.ts MapState declares (the additive hybrid fields
# drones/frame are checked explicitly below).
_REQUIRED_KEYS = {
    "missionName", "region", "startedAt", "loop", "confidenceToDeclare", "declareThreshold",
    "stats", "layers", "detections", "waypoints", "flightPath", "dronePos", "heatBlobs",
    "trend", "recentCommands", "telemetry",
}


def test_endpoints_serve_valid_shapes():
    """
    Scenario: hit /health, /state, /map_base.png, /located on a freshly-started server.
    Why it matters: the dashboard polls these from the first instant; /state must be a complete
    UI-MapState carrying the fleet (drones[]) + frame, /map_base.png must serve a PNG keyed to the
    frame, and /health/located must report cleanly.
    """
    from fastapi.testclient import TestClient
    import integration.server as server

    with TestClient(server.app) as client:
        assert client.get("/health").json()["status"] == "ok"

        state = client.get("/state").json()
        assert _REQUIRED_KEYS.issubset(state.keys())
        assert "frame" in state and isinstance(state["drones"], list)
        assert len(state["drones"]) == 3  # the 3-drone scenario
        for d in state["drones"]:
            assert set(d.keys()) == {"id", "color", "pos", "path"}

        base = client.get(f"/map_base.png?v={state['frame']}")
        assert base.status_code == 200
        assert base.headers["content-type"] == "image/png"
        assert base.content[:8] == b"\x89PNG\r\n\x1a\n"

        assert isinstance(client.get("/located").json(), dict)


def test_server_runs_through_guidance_to_arrived(monkeypatch):
    """
    Scenario: run the server flat-out and poll until the guide-home phase reports 'arrived'.
    Why it matters: the full hybrid story through HTTP — the 3-drone search locates, the server
    streams the guide-home, and /state exposes the route + moving subject + operators, finishing
    'arrived' with /located set, confidence 100, and the Guide Home ribbon step done.
    """
    import integration.server as server

    monkeypatch.setattr(server, "_STEP_INTERVAL_S", 0.0)

    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        client.post("/reset")

        deadline = time.time() + 25.0
        health = client.get("/health").json()
        while health["guidance_status"] != "arrived" and time.time() < deadline:
            time.sleep(0.05)
            health = client.get("/health").json()

        assert health["guidance_status"] == "arrived", f"did not reach arrived: {health}"

        located = client.get("/located").json()
        assert "cell" in located and len(located["cell"]) == 2

        state = client.get("/state").json()
        assert state["confidenceToDeclare"] == 100
        assert state["stats"]["personsFound"] == 1
        assert state["guidanceStatus"] == "arrived"
        assert state["guidancePath"] and len(state["guidancePath"]) >= 2
        assert state["subjectPos"] is not None and state["operatorPos"] is not None
        guide_step = next(s for s in state["loop"] if s["label"] == "Guide Home")
        assert guide_step["status"] == "done"


def test_subject_broadcast_appears_once_located(monkeypatch):
    """
    Scenario: run flat-out to the locate; inspect /state at the start vs. after locating.
    Why it matters: the spoken broadcast is the demo's high point — it must be ABSENT during the
    search and then carry the composed message (English + Spanish) once located. (Reads /state
    only — no Deepgram call.)
    """
    import integration.server as server

    monkeypatch.setattr(server, "_STEP_INTERVAL_S", 0.0)
    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        client.post("/reset")
        assert client.get("/state").json()["subjectBroadcast"] is None  # frame 0: searching

        deadline = time.time() + 25.0
        h = client.get("/health").json()
        while not h["located"] and time.time() < deadline:
            time.sleep(0.05)
            h = client.get("/health").json()
        assert h["located"]

        bc = client.get("/state").json()["subjectBroadcast"]
        assert bc is not None
        assert "en" in bc["texts"] and "es" in bc["texts"]
        assert "stay" in bc["texts"]["en"].lower()
        assert "en" in bc["langs"]


def test_broadcast_mp3_serves_audio_when_synthesized(monkeypatch):
    """
    Scenario: force Deepgram synthesis to return fake bytes (NO live call); request the audio.
    Why it matters: pins the /broadcast.mp3 plumbing — once located it serves audio/mpeg for a
    supported language (en) and 404s for an unsupported one (es -> browser-TTS fallback).
    """
    import integration.server as server

    monkeypatch.setattr(server, "_STEP_INTERVAL_S", 0.0)
    monkeypatch.setattr(server, "synthesize", lambda text, voice="x": b"FAKE_MP3")  # never hits Deepgram
    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        client.post("/reset")  # clears the audio cache so our mock is used
        deadline = time.time() + 25.0
        h = client.get("/health").json()
        while not h["located"] and time.time() < deadline:
            time.sleep(0.05)
            h = client.get("/health").json()
        assert h["located"]

        en = client.get("/broadcast.mp3?lang=en")
        assert en.status_code == 200
        assert en.headers["content-type"] == "audio/mpeg"
        assert en.content == b"FAKE_MP3"

        assert client.get("/broadcast.mp3?lang=es").status_code == 404  # no Aura Spanish voice -> fallback


def test_map_base_changes_during_search(monkeypatch):
    """
    Scenario: capture the base image at an early search frame and a later one.
    Why it matters: the base is rendered PER frame during the search (the belief + drones' sectors
    evolve), so two different search frames should yield different image bytes — proving the map
    is live, not static.
    """
    import integration.server as server

    monkeypatch.setattr(server, "_STEP_INTERVAL_S", 0.0)

    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        client.post("/reset")
        early = client.get("/map_base.png?v=1").content
        # let the run advance a few frames
        time.sleep(0.5)
        h = client.get("/health").json()
        mid = max(2, h["n_search"] // 2)
        later = client.get(f"/map_base.png?v={mid}").content
        assert early[:8] == b"\x89PNG\r\n\x1a\n" and later[:8] == b"\x89PNG\r\n\x1a\n"
        assert early != later, "base image did not change between search frames"


# Keys /ops must always carry — the contract the operator agent's sar_service reads
# (and the offline snapshot mirrors).
_OPS_KEYS = {
    "status", "located", "n_drones", "elapsed", "coverage_pct", "coverage_km2",
    "confidence_pct", "highest_prob", "located_info",
}


def test_ops_shape_while_searching():
    """
    Scenario: hit /ops on a freshly-started server (frame 0, still searching).
    Why it matters: the operator voice agent reads /ops for spoken status; before the locate it
    must report searching, no located_info, the 3-drone fleet, and a highest-probability area
    described by a landmark (so the agent never reads raw coordinates aloud).
    """
    from fastapi.testclient import TestClient
    import integration.server as server

    with TestClient(server.app) as client:
        ops = client.get("/ops").json()
        assert _OPS_KEYS.issubset(ops.keys())
        assert ops["status"] == "searching"
        assert ops["located"] is False
        assert ops["located_info"] is None
        assert ops["n_drones"] == 3
        assert 0.0 <= ops["coverage_pct"] <= 100.0
        assert "Pantoll" in ops["highest_prob"]["description"]


def test_ops_reflects_located(monkeypatch):
    """
    Scenario: run flat-out to the locate, then read /ops.
    Why it matters: once the brain declares located, /ops must flip to located with a speakable
    located_info (terrain phrase + landmark + lat/lon) and full confidence — the facts the agent
    speaks when the operator asks 'did we find them?'.
    """
    import integration.server as server

    monkeypatch.setattr(server, "_STEP_INTERVAL_S", 0.0)
    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        client.post("/reset")

        deadline = time.time() + 25.0
        h = client.get("/health").json()
        while not h["located"] and time.time() < deadline:
            time.sleep(0.05)
            h = client.get("/health").json()
        assert h["located"]

        ops = client.get("/ops").json()
        assert ops["status"] == "located"
        assert ops["located"] is True
        info = ops["located_info"]
        assert info is not None
        assert info["terrain"] == "in the trees"  # the subject is in tree cover
        assert "Pantoll" in info["description"]
        assert len(info["latlon"]) == 2
        assert ops["confidence_pct"] == 100
