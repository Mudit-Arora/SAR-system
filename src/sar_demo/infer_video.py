from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass
class Detection:
    xyxy: Tuple[int, int, int, int]
    conf: float
    cls_id: int
    class_name: str
    track_id: Optional[int] = None
    alert_score: float = 0.0
    crop_path: str = ""


class SimpleCentroidTracker:
    def __init__(self, max_distance: float = 90.0, max_missing: int = 30) -> None:
        self.max_distance = max_distance
        self.max_missing = max_missing
        self.next_id = 1
        self.tracks: Dict[int, Dict[str, object]] = {}

    @staticmethod
    def centroid(box: Tuple[int, int, int, int]) -> np.ndarray:
        x1, y1, x2, y2 = box
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0])

    def update(self, detections: Sequence[Detection]) -> List[int]:
        if not detections:
            self._age_tracks([])
            return []

        det_centroids = [self.centroid(det.xyxy) for det in detections]
        assigned_ids: List[Optional[int]] = [None] * len(detections)
        track_ids = list(self.tracks.keys())

        candidate_pairs = []
        for track_id in track_ids:
            track_centroid = self.tracks[track_id]["centroid"]
            for det_idx, det_centroid in enumerate(det_centroids):
                distance = float(np.linalg.norm(track_centroid - det_centroid))
                if distance <= self.max_distance:
                    candidate_pairs.append((distance, track_id, det_idx))
        candidate_pairs.sort(key=lambda item: item[0])

        used_tracks = set()
        used_detections = set()
        for _, track_id, det_idx in candidate_pairs:
            if track_id in used_tracks or det_idx in used_detections:
                continue
            assigned_ids[det_idx] = track_id
            self.tracks[track_id]["centroid"] = det_centroids[det_idx]
            self.tracks[track_id]["missing"] = 0
            used_tracks.add(track_id)
            used_detections.add(det_idx)

        for det_idx, track_id in enumerate(assigned_ids):
            if track_id is not None:
                continue
            track_id = self.next_id
            self.next_id += 1
            assigned_ids[det_idx] = track_id
            self.tracks[track_id] = {"centroid": det_centroids[det_idx], "missing": 0}

        self._age_tracks(list(assigned_ids))
        return [int(track_id) for track_id in assigned_ids if track_id is not None]

    def _age_tracks(self, active_ids: Sequence[int]) -> None:
        active = set(active_ids)
        stale = []
        for track_id, track in self.tracks.items():
            if track_id in active:
                continue
            track["missing"] = int(track["missing"]) + 1
            if int(track["missing"]) > self.max_missing:
                stale.append(track_id)
        for track_id in stale:
            del self.tracks[track_id]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run YOLO SAR detection/tracking on a drone video.")
    parser.add_argument("--model", required=True, type=Path, help="YOLO weights, usually runs/.../best.pt.")
    parser.add_argument("--video", required=True, type=Path, help="Input drone footage.")
    parser.add_argument("--output", default=None, type=Path, help="Annotated video path.")
    parser.add_argument("--conf", default=0.25, type=float)
    parser.add_argument("--iou", default=0.5, type=float)
    parser.add_argument("--imgsz", default=960, type=int)
    parser.add_argument("--device", default=None, help="Device for Ultralytics inference.")
    parser.add_argument(
        "--tracker",
        default="bytetrack",
        choices=["bytetrack", "botsort", "simple"],
        help="Use Ultralytics tracking when available, otherwise fallback to simple centroid tracking.",
    )
    parser.add_argument("--crop-dir", default=Path("outputs/crops"), type=Path)
    parser.add_argument("--crop-every", default=15, type=int, help="Save alert crops every N frames per track.")
    parser.add_argument("--crop-classes", default="person", help="Comma-separated class names to crop.")
    parser.add_argument("--no-crops", action="store_true")
    return parser


def import_yolo():
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Ultralytics is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    return YOLO


def parse_results(result, names: Dict[int, str]) -> List[Detection]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    xyxy = boxes.xyxy.cpu().numpy().astype(int)
    confs = boxes.conf.cpu().numpy()
    classes = boxes.cls.cpu().numpy().astype(int)
    if boxes.id is not None:
        track_ids: List[Optional[int]] = [int(value) for value in boxes.id.cpu().numpy()]
    else:
        track_ids = [None] * len(xyxy)

    detections: List[Detection] = []
    for box, conf, cls_id, track_id in zip(xyxy, confs, classes, track_ids):
        x1, y1, x2, y2 = [int(value) for value in box]
        detections.append(
            Detection(
                xyxy=(x1, y1, x2, y2),
                conf=float(conf),
                cls_id=int(cls_id),
                class_name=names.get(int(cls_id), str(cls_id)),
                track_id=track_id,
            )
        )
    return detections


def draw_detection(frame: np.ndarray, detection: Detection) -> None:
    x1, y1, x2, y2 = detection.xyxy
    color = (56, 189, 248) if detection.class_name.lower() == "person" else (245, 158, 11)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    label = (
        f"id {detection.track_id} {detection.class_name} "
        f"{detection.conf:.2f} alert {detection.alert_score:.2f}"
    )
    label_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    label_y = max(y1, label_size[1] + 8)
    cv2.rectangle(
        frame,
        (x1, label_y - label_size[1] - 8),
        (x1 + label_size[0] + 8, label_y + baseline),
        color,
        -1,
    )
    cv2.putText(
        frame,
        label,
        (x1 + 4, label_y - 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (15, 23, 42),
        1,
        cv2.LINE_AA,
    )


def update_track_stats(
    stats: Dict[int, dict],
    detection: Detection,
    frame_idx: int,
    frame_shape: Tuple[int, int, int],
) -> None:
    if detection.track_id is None:
        return

    x1, y1, x2, y2 = detection.xyxy
    box_h = max(1, y2 - y1)
    record = stats[detection.track_id]
    if not record:
        record.update(
            {
                "first_frame": frame_idx,
                "hits": 0,
                "conf_sum": 0.0,
                "best_conf": 0.0,
                "best_alert": 0.0,
                "class_counts": Counter(),
                "last_bbox": "",
            }
        )

    record["last_frame"] = frame_idx
    record["hits"] += 1
    record["conf_sum"] += detection.conf
    record["best_conf"] = max(float(record["best_conf"]), detection.conf)
    record["class_counts"][detection.class_name] += 1
    record["last_bbox"] = f"{x1},{y1},{x2},{y2}"

    persistence_score = min(float(record["hits"]) / 8.0, 1.0)
    size_score = min(float(box_h) / 32.0, 1.0)
    detection.alert_score = (0.65 * detection.conf) + (0.25 * persistence_score) + (0.10 * size_score)
    record["best_alert"] = max(float(record["best_alert"]), detection.alert_score)


def save_crop(
    frame: np.ndarray,
    detection: Detection,
    crop_dir: Path,
    video_stem: str,
    frame_idx: int,
) -> str:
    x1, y1, x2, y2 = detection.xyxy
    height, width = frame.shape[:2]
    x1 = max(0, min(width - 1, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height - 1, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return ""

    crop_dir.mkdir(parents=True, exist_ok=True)
    path = crop_dir / f"{video_stem}_f{frame_idx:06d}_id{detection.track_id}_{detection.class_name}.jpg"
    cv2.imwrite(str(path), frame[y1:y2, x1:x2])
    return str(path)


def write_track_summary(summary_path: Path, stats: Dict[int, dict], fps: float) -> None:
    with summary_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "track_id",
                "class_name",
                "first_frame",
                "last_frame",
                "start_time_s",
                "end_time_s",
                "hits",
                "best_conf",
                "mean_conf",
                "best_alert",
                "last_bbox",
            ],
        )
        writer.writeheader()
        for track_id, record in sorted(stats.items()):
            if not record:
                continue
            class_name = record["class_counts"].most_common(1)[0][0]
            hits = int(record["hits"])
            writer.writerow(
                {
                    "track_id": track_id,
                    "class_name": class_name,
                    "first_frame": record["first_frame"],
                    "last_frame": record["last_frame"],
                    "start_time_s": round(float(record["first_frame"]) / fps, 3) if fps else 0.0,
                    "end_time_s": round(float(record["last_frame"]) / fps, 3) if fps else 0.0,
                    "hits": hits,
                    "best_conf": round(float(record["best_conf"]), 4),
                    "mean_conf": round(float(record["conf_sum"]) / max(hits, 1), 4),
                    "best_alert": round(float(record["best_alert"]), 4),
                    "last_bbox": record["last_bbox"],
                }
            )


def run(args: argparse.Namespace) -> None:
    if not args.model.exists():
        raise SystemExit(f"Model weights not found: {args.model}")
    if not args.video.exists():
        raise SystemExit(f"Video not found: {args.video}")

    YOLO = import_yolo()
    model = YOLO(str(args.model))
    names = {int(key): str(value) for key, value in model.names.items()}

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {args.video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output = args.output or Path("outputs") / f"{args.video.stem}_annotated.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    detections_csv = output.with_name(f"{output.stem}_detections.csv")
    tracks_csv = output.with_name(f"{output.stem}_tracks.csv")

    simple_tracker = SimpleCentroidTracker()
    track_stats: Dict[int, dict] = defaultdict(dict)
    crop_classes = {name.strip().lower() for name in args.crop_classes.split(",") if name.strip()}
    last_crop_frame: Dict[int, int] = defaultdict(lambda: -10**9)
    tracking_mode = args.tracker

    infer_kwargs = {"conf": args.conf, "iou": args.iou, "imgsz": args.imgsz, "verbose": False}
    if args.device:
        infer_kwargs["device"] = args.device

    with detections_csv.open("w", encoding="utf-8", newline="") as csv_file:
        fieldnames = [
            "frame",
            "time_s",
            "track_id",
            "class_id",
            "class_name",
            "conf",
            "alert_score",
            "x1",
            "y1",
            "x2",
            "y2",
            "crop_path",
        ]
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        csv_writer.writeheader()

        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if tracking_mode in {"bytetrack", "botsort"}:
                try:
                    results = model.track(
                        frame,
                        persist=True,
                        tracker=f"{tracking_mode}.yaml",
                        **infer_kwargs,
                    )
                    detections = parse_results(results[0], names)
                    if any(det.track_id is None for det in detections):
                        ids = simple_tracker.update(detections)
                        for det, track_id in zip(detections, ids):
                            det.track_id = track_id
                except Exception as exc:
                    print(f"Ultralytics {tracking_mode} unavailable ({exc}); using simple tracker.")
                    tracking_mode = "simple"
                    results = model.predict(frame, **infer_kwargs)
                    detections = parse_results(results[0], names)
                    ids = simple_tracker.update(detections)
                    for det, track_id in zip(detections, ids):
                        det.track_id = track_id
            else:
                results = model.predict(frame, **infer_kwargs)
                detections = parse_results(results[0], names)
                ids = simple_tracker.update(detections)
                for det, track_id in zip(detections, ids):
                    det.track_id = track_id

            for detection in detections:
                update_track_stats(track_stats, detection, frame_idx, frame.shape)
                if (
                    not args.no_crops
                    and detection.track_id is not None
                    and detection.class_name.lower() in crop_classes
                    and frame_idx - last_crop_frame[detection.track_id] >= args.crop_every
                ):
                    detection.crop_path = save_crop(
                        frame, detection, args.crop_dir, args.video.stem, frame_idx
                    )
                    last_crop_frame[detection.track_id] = frame_idx

                draw_detection(frame, detection)
                x1, y1, x2, y2 = detection.xyxy
                csv_writer.writerow(
                    {
                        "frame": frame_idx,
                        "time_s": round(frame_idx / fps, 3),
                        "track_id": detection.track_id,
                        "class_id": detection.cls_id,
                        "class_name": detection.class_name,
                        "conf": round(detection.conf, 4),
                        "alert_score": round(detection.alert_score, 4),
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "crop_path": detection.crop_path,
                    }
                )

            writer.write(frame)
            frame_idx += 1

    cap.release()
    writer.release()
    write_track_summary(tracks_csv, track_stats, fps)

    print(f"Annotated video: {output}")
    print(f"Detections CSV: {detections_csv}")
    print(f"Track summary: {tracks_csv}")
    if not args.no_crops:
        print(f"Crops directory: {args.crop_dir}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
