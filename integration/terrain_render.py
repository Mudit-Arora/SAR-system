# =============================================================================
# integration/terrain_render.py
# -----------------------------------------------------------------------------
# Responsible for: Rendering the real Marin terrain to a muted, colorized PNG that the
#                  dashboard shows BEHIND the probability heatmap — shaded relief tinted by
#                  elevation, deliberately darkened so the heat overlay stays the focus.
# Role in project: The terrain side of the "show the real region" feature. Reuses the
#                  showcase's proven hillshade (DRY) and renders it in the SAME grid frame as
#                  the posterior, so no reprojection is needed — the dashboard just stretches
#                  this image to the map box and every overlay lines up by construction.
# Assumptions: The real DEM raster exists (data/terrain/); render_terrain_png raises
#              FileNotFoundError if not, so the server can fall back to its procedural backdrop.
#              North-up output (flipud): grid row 0 is SOUTH, the UI's y points down, matching
#              dashboard_projection._cell_to_norm and the map's "N" compass.
# =============================================================================

from __future__ import annotations

import io

import numpy as np
from PIL import Image

# Reuse the showcase's Lambert hillshade (DRY) rather than re-deriving it. This pulls
# matplotlib, which is fine here: terrain rendering is a server-only path and matplotlib is
# already a project dependency.
from src.demo.showcase import hillshade
from src.search.terrain_raster import _DEFAULT_DEM, sample_raster_to_grid

# Output is upscaled from the (~160x160) grid so the backdrop isn't blocky when stretched to a
# ~700px map panel. The hillshade detail is grid-limited anyway, so a smooth bicubic upscale is
# all we need (no finer raster sampling).
_OUTPUT_PX = 640

# --- Tuning knobs for "muted/darkened so the heatmap stays the focus" ---
# saturation < 1 pulls the elevation tint toward gray (less color competition with the heat).
# relief_floor keeps shadowed valleys from going pure black (terrain stays readable).
# brightness scales the whole backdrop down: a darker base makes the screen-blended heat pop.
_SATURATION = 0.55
_RELIEF_FLOOR = 0.35
_BRIGHTNESS = 0.6


def render_terrain_png(
    grid,
    *,
    cmap_name: str = "gist_earth",
    saturation: float = _SATURATION,
    relief_floor: float = _RELIEF_FLOOR,
    brightness: float = _BRIGHTNESS,
    size_px: int = _OUTPUT_PX,
) -> bytes:
    """
    Render the terrain backdrop for a grid as muted, colorized shaded relief (PNG bytes).

    Args:
        grid: The shared GridSpec the loop runs on (fixes the geographic frame).
        cmap_name: A matplotlib colormap for the elevation tint. gist_earth (dark->green->
            brown->white) reads as land relief; a parameter so it's easy to swap.
        saturation: How much elevation COLOR to keep, in [0, 1]. <1 desaturates toward gray
            so the tint doesn't compete with the heatmap. 0 = pure grayscale hillshade.
        relief_floor: Lower bound of the hillshade multiplier, so shadowed slopes keep some
            tint instead of crushing to black.
        brightness: Overall darkening factor in [0, 1]. Lower = darker backdrop = the
            lightening mix-blend-screen heat overlay pops harder.
        size_px: Square output edge; the grid image is bicubic-upscaled to this for smoothness.

    Returns:
        PNG-encoded bytes (RGB), north-up, ready to serve as image/png.

    Raises:
        FileNotFoundError: If the DEM raster is absent (the caller falls back to a procedural
            backdrop). Propagated from sample_raster_to_grid.

    Why:
        This is the whole terrain feature in one pure function: elevation -> color -> shaded by
        relief -> muted -> north-up image. Keeping it pure (grid in, bytes out) makes it
        trivially testable and lets the server cache the result (terrain is static per run).
    """
    import matplotlib  # local import keeps this module's top-level import lighter

    # 1) Elevation onto the grid (meters). Off-DEM cells come back NaN; fill with the median so
    #    the colormap + hillshade are defined everywhere (those cells read as flat mid terrain).
    dem = sample_raster_to_grid(str(_DEFAULT_DEM), grid)
    dem = np.where(np.isnan(dem), np.nanmedian(dem), dem)

    # 2) Normalize elevation to [0, 1] over a ROBUST range (2nd-98th percentile) so a couple of
    #    outlier cells (a lone peak/pit) don't compress the whole tint into one band.
    lo, hi = np.percentile(dem, 2), np.percentile(dem, 98)
    norm = np.clip((dem - lo) / (hi - lo + 1e-9), 0.0, 1.0)

    # 3) Elevation -> RGB via the colormap (drop the alpha channel).
    cmap = matplotlib.colormaps[cmap_name]
    rgb = cmap(norm)[..., :3]  # (n_rows, n_cols, 3) in [0, 1]

    # 4) Desaturate toward luminance so the tint is muted (less color competition with heat).
    luma = rgb.mean(axis=-1, keepdims=True)
    rgb = luma + saturation * (rgb - luma)

    # 5) Shade by the hillshade (colored shaded relief). The floor keeps valleys from black.
    shade = hillshade(grid)[..., None]  # (n_rows, n_cols, 1) in [0, 1]
    rgb = rgb * (relief_floor + (1.0 - relief_floor) * shade)

    # 6) Darken the whole backdrop so the heatmap is the visual focus.
    rgb = np.clip(rgb * brightness, 0.0, 1.0)

    # 7) North-up: grid row 0 is south, but image row 0 is the top, so flip vertically.
    rgb = np.flipud(rgb)

    # 8) Encode: grid-res RGB -> bicubic upscale -> PNG bytes.
    img = Image.fromarray((rgb * 255.0).astype(np.uint8), mode="RGB")
    if size_px and size_px != img.width:
        img = img.resize((size_px, size_px), Image.BICUBIC)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
