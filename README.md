# SAR Drone Footage Detection Demo

This project is set up for a prerecorded drone-footage search-and-rescue demo:

```text
Drone video or frame dataset
  -> YOLO person detector fine-tuned on UAV thermal/RGB data
  -> temporal tracking during video inference
  -> annotated video + detection CSV + alert crops
```

## Recommended Dataset Plan

Use **WiSARD** as the main SAR dataset because it is UAV wilderness search-and-rescue data with visual and thermal imagery. Add **HIT-UAV** for extra thermal person/vehicle examples.

- WiSARD paper: https://arxiv.org/abs/2309.04453
- HIT-UAV paper: https://arxiv.org/abs/2204.03245
- HIT-UAV repo: https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset

For your demo, start with one detector:

```text
Thermal footage: YOLO11s fine-tuned on WiSARD thermal + HIT-UAV
RGB footage:     YOLO11s fine-tuned on WiSARD RGB
```

Then run the video demo script to add tracking, alert crops, and CSV output.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Dataset Layout

Put YOLO-format datasets under `data/processed/`.

```text
data/processed/wizard_thermal_person/
  images/train/
  images/val/
  images/test/
  labels/train/
  labels/val/
  labels/test/
```

Each label file uses standard YOLO detection format:

```text
class_id x_center y_center width height
```

Coordinates must be normalized from `0.0` to `1.0`.

## Check A Dataset

```bash
python -m sar_demo.dataset_tools check \
  --data configs/datasets/wizard_thermal_person.yaml
```

## Train Thermal Detector

```bash
python -m sar_demo.train_yolo \
  --data configs/datasets/wizard_thermal_person.yaml \
  --model yolo11s.pt \
  --imgsz 960 \
  --epochs 80 \
  --batch 8 \
  --name thermal_person_yolo11s
```

Use `--imgsz 1280` if your GPU can handle it. Tiny people in aerial footage suffer badly when images are downscaled too much.

## Train HIT-UAV Thermal Baseline

Your HIT-UAV data should be arranged in YOLO format under `data/hit-uav/`:

```text
data/hit-uav/
  images/train/
  images/val/
  images/test/
  labels/train/
  labels/val/
  labels/test/
```

```bash
python -m sar_demo.train_yolo \
  --data configs/datasets/hit_uav_thermal.yaml \
  --model yolo11s.pt \
  --imgsz 960 \
  --epochs 60 \
  --batch 8 \
  --name hit_uav_yolo11s
```

Shortcut:

```bash
./scripts/train_hit_uav.sh
```

On a CPU-only machine, use this quick sanity check before a real GPU run:

```bash
./scripts/train_hit_uav_cpu_quick.sh
```

## Train On Kaggle

Use [notebooks/train_hit_uav_kaggle.ipynb](notebooks/train_hit_uav_kaggle.ipynb) when training on Kaggle. Attach the HIT-UAV folder as a Kaggle Dataset and enable a GPU accelerator. The notebook auto-discovers the dataset root, rewrites the dataset YAML for Kaggle paths, trains YOLO11s, validates on `val` and `test`, and packages the trained weights as `hit_uav_yolo11s_results.zip`.

## Run Demo On Drone Footage

Put a video in `data/demo_footage/`, then run:

```bash
python -m sar_demo.infer_video \
  --model models/model.pt \
  --video data/demo_footage/thermal_demo.mp4 \
  --output outputs/thermal_demo_annotated.mp4 \
  --conf 0.25 \
  --imgsz 960
```

Outputs:

- annotated video: `outputs/thermal_demo_annotated.mp4`
- per-frame detections CSV: `outputs/thermal_demo_annotated_detections.csv`
- per-track summary CSV: `outputs/thermal_demo_annotated_tracks.csv`
- cropped alert images: `outputs/crops/`

## Run On Natural RGB Drone Footage

The HIT-UAV model is trained on thermal images, so it is not the right model for normal color drone footage. For natural RGB video, start with the regular RGB YOLO model:

```bash
./scripts/run_rgb_demo.sh yolo11s.pt data/demo_footage/real_drone_video.mp4 outputs/real_drone_annotated.mp4
```

For better RGB drone accuracy, fine-tune on an RGB drone dataset such as VisDrone or Stanford Drone Dataset, then pass the fine-tuned RGB weights to `run_rgb_demo.sh`.

## Best Demo Story

Say this:

> This prototype analyzes prerecorded UAV footage, detects possible victims, tracks them across frames, and exports high-confidence alerts for human review.

Avoid claiming autonomous rescue or guaranteed human identification. Thermal or RGB detection should be treated as a candidate generator that still needs review.
