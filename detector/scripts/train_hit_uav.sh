#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
export YOLO_CONFIG_DIR="${YOLO_CONFIG_DIR:-/tmp/Ultralytics}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib}"

"$PYTHON_BIN" -m sar_demo.train_yolo \
  --data configs/datasets/hit_uav_thermal.yaml \
  --model yolo11s.pt \
  --imgsz 960 \
  --epochs 60 \
  --batch 8 \
  --name hit_uav_yolo11s
