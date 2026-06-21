#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
export YOLO_CONFIG_DIR="${YOLO_CONFIG_DIR:-/tmp/Ultralytics}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib}"

"$PYTHON_BIN" -m sar_demo.train_yolo \
  --data configs/datasets/wizard_thermal_person.yaml \
  --model yolo11s.pt \
  --imgsz 960 \
  --epochs 80 \
  --batch 8 \
  --name thermal_person_yolo11s
