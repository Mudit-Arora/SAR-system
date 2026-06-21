#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${1:-runs/detect/thermal_person_yolo11s/weights/best.pt}"
VIDEO_PATH="${2:-data/demo_footage/thermal_demo.mp4}"
OUTPUT_PATH="${3:-outputs/thermal_demo_annotated.mp4}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
export YOLO_CONFIG_DIR="${YOLO_CONFIG_DIR:-/tmp/Ultralytics}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib}"

"$PYTHON_BIN" -m sar_demo.infer_video \
  --model "$MODEL_PATH" \
  --video "$VIDEO_PATH" \
  --output "$OUTPUT_PATH" \
  --conf 0.25 \
  --imgsz 960
