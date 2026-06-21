#!/usr/bin/env python3
# =============================================================================
# check_setup.py
# -----------------------------------------------------------------------------
# Responsible for: Verifying the gitignored terrain rasters the brain needs are
#                  present at the right path AND intact (not truncated/altered by
#                  the out-of-band transfer used to share them — e.g. Slack).
# Role in project: A self-serve diagnostic for a fresh laptop. The integration
#                  server builds the real-terrain run AT STARTUP, so a missing or
#                  corrupt raster makes the server crash and the dashboard map
#                  (/map_base.png) never loads. This pinpoints that before you
#                  waste time wondering why the image is blank.
# Usage (from the repo root, with the main venv):
#     .venv/bin/python check_setup.py
# =============================================================================
"""Verify the two terrain rasters are present and byte-for-byte intact."""
import hashlib
import pathlib
import sys

# Canonical copies (the ones the working demo uses). Your files MUST match these
# exactly — a different size or md5 means the transfer corrupted the file.
EXPECTED = {
    "data/terrain/dem_marin_usgs10m.tif": (19350271, "d5d5d4e5b64353702be1f166df46ca04"),
    "data/terrain/worldcover_2021_N36W123.tif": (87597650, "6038fdc8623cce445f45f14bd9cf383d"),
}


def md5_of(path: pathlib.Path, chunk: int = 1 << 20) -> str:
    """Stream the file through md5 (chunked so an 84 MB file doesn't load into RAM)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    root = pathlib.Path(__file__).parent
    all_ok = True

    for rel, (exp_size, exp_md5) in EXPECTED.items():
        path = root / rel
        print(f"\n{rel}")

        if not path.exists():
            print("  X MISSING — place the file here with this EXACT name/path.")
            print("    (Check it didn't land in Downloads, get renamed to '... (1).tif', etc.)")
            all_ok = False
            continue

        size = path.stat().st_size
        if size != exp_size:
            print(f"  X WRONG SIZE: {size:,} bytes, expected {exp_size:,}.")
            print("    The transfer truncated/altered it. Re-send it ZIPPED (don't paste it")
            print("    inline as an image — that can recompress a .tif).")
            all_ok = False
            continue

        actual_md5 = md5_of(path)
        if actual_md5 != exp_md5:
            print(f"  X CORRUPT: md5 {actual_md5}, expected {exp_md5}.")
            print("    Same size but different bytes — re-send as a zip.")
            all_ok = False
            continue

        # Sizes + hash match; confirm the GIS library can actually open it.
        try:
            import rasterio  # imported lazily so a missing-file check works without GDAL
            with rasterio.open(path) as ds:
                bounds = tuple(round(b, 3) for b in ds.bounds)
                print(f"  OK — {size:,} bytes, md5 matches, rasterio bounds {bounds}")
        except Exception as exc:  # noqa: BLE001 - report any open failure plainly
            print(f"  X UNREADABLE by rasterio: {exc}")
            all_ok = False

    print()
    if all_ok:
        print("ALL GOOD: both rasters are present and intact.")
        print("If the map STILL doesn't load, the issue is downstream — make sure the")
        print("integration server is running (.venv/bin/uvicorn integration.server:app")
        print("--port 8000) and the dashboard can reach it at http://localhost:8000.")
    else:
        print("FIX THE ABOVE: the integration server can't build without intact rasters,")
        print("so it crashes at startup and /map_base.png never loads.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
