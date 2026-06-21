# =============================================================================
# tests/test_integration_terrain_render.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the terrain backdrop renderer (integration/terrain_render.py)
#                  emits a valid, non-degenerate, deterministic PNG in the grid frame.
# Role in project: Guards the terrain feature's core. The dashboard stretches this image
#                  behind the heatmap, so it must be a real RGB PNG of the expected size with
#                  actual relief variation (not a blank/solid fill) and muted enough that the
#                  heat overlay stays the focus.
# Assumptions: The real DEM raster exists (data/terrain/). If it doesn't, the render is
#              skipped — the renderer is allowed to raise FileNotFoundError there (the server
#              falls back to a procedural backdrop), so this suite shouldn't fail on a machine
#              without the rasters.
# =============================================================================

from __future__ import annotations

import io
import pathlib

import numpy as np
import pytest
from PIL import Image

from src.common.config import BrainConfig
from src.common.grid import GridSpec
from src.search.terrain_raster import _DEFAULT_DEM

# Skip the whole module if the DEM raster isn't present (CI / a fresh clone without data/).
_HAS_DEM = pathlib.Path(_DEFAULT_DEM).exists()
pytestmark = pytest.mark.skipif(not _HAS_DEM, reason="real DEM raster not present in data/terrain/")


def _render():
    """Render the terrain PNG once for the default grid. Why: shared setup for the assertions."""
    from integration.terrain_render import render_terrain_png

    grid = GridSpec.from_config(BrainConfig())
    return render_terrain_png(grid, size_px=256)  # smaller for a fast test


def test_render_is_a_valid_rgb_png_of_expected_size():
    """
    Scenario: render the terrain and decode the bytes.
    Why it matters: the server serves these bytes as image/png and the browser must decode them;
    assert they're a real PNG, RGB, and the requested size (so the dashboard stretch is predictable).
    """
    png = _render()
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.mode == "RGB"
    assert img.size == (256, 256)


def test_render_has_relief_variation_and_is_muted():
    """
    Scenario: inspect the pixel statistics of the rendered terrain.
    Why it matters: the backdrop must actually SHOW terrain (real variation, not a solid fill)
    AND stay muted/dark so the heatmap remains the focus. Assert non-trivial variance and a
    mean brightness comfortably below mid-gray (the deliberate darkening).
    """
    img = Image.open(io.BytesIO(_render())).convert("RGB")
    arr = np.asarray(img, dtype=float) / 255.0

    assert arr.std() > 0.02, "terrain looks flat/solid — no relief variation"
    assert arr.mean() < 0.5, "terrain is too bright — would compete with the heatmap"


def test_render_is_deterministic():
    """
    Scenario: render the same grid twice.
    Why it matters: the server caches the terrain image once per run; rendering must be
    deterministic so the cached bytes are stable and a /reset re-renders identically.
    """
    assert _render() == _render()
