#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-data/raw/HIT-UAV-Infrared-Thermal-Dataset}"

git clone --depth 1 \
  https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset.git \
  "$TARGET_DIR"
