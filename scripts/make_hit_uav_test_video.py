from __future__ import annotations

import argparse
from pathlib import Path

import cv2


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a demo MP4 from HIT-UAV image frames.")
    parser.add_argument(
        "--source",
        default=Path("data/hit-uav/images/test"),
        type=Path,
        help="Directory containing HIT-UAV image frames.",
    )
    parser.add_argument(
        "--output",
        default=Path("data/demo_footage/hit_uav_frames_test_640x512.mp4"),
        type=Path,
        help="Output video path.",
    )
    parser.add_argument("--fps", default=8, type=float, help="Output video FPS.")
    parser.add_argument("--limit", default=300, type=int, help="Maximum number of frames to include.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    images = sorted(
        path
        for path in args.source.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        raise SystemExit(f"No images found in {args.source}")
    if args.limit > 0:
        images = images[: args.limit]

    first = cv2.imread(str(images[0]))
    if first is None:
        raise SystemExit(f"Could not read first image: {images[0]}")

    height, width = first.shape[:2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(args.output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        args.fps,
        (width, height),
    )

    written = 0
    for image_path in images:
        frame = cv2.imread(str(image_path))
        if frame is None:
            continue
        if frame.shape[:2] != (height, width):
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        writer.write(frame)
        written += 1

    writer.release()
    print(f"Wrote {written} frames to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
