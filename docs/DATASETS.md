# Datasets

## Best Choice For This Demo

Use **WiSARD** first. It matches the search-and-rescue story best because it contains UAV visual and thermal imagery collected for wilderness SAR scenarios.

Use **HIT-UAV** second. It is thermal UAV data with people and vehicles, useful for improving thermal detection and teaching the model common hot false positives around roads, lots, and buildings.

## Expected YOLO Layout

Every config in `configs/datasets/` expects this structure:

```text
data/processed/<dataset_name>/
  images/train/*.jpg
  images/val/*.jpg
  images/test/*.jpg
  labels/train/*.txt
  labels/val/*.txt
  labels/test/*.txt
```

For each image:

```text
images/train/example_001.jpg
labels/train/example_001.txt
```

Label rows:

```text
class_id x_center y_center width height
```

All box coordinates are normalized from `0.0` to `1.0`.

## Suggested Splits

Use flight/session-level splits if the dataset has multiple flights:

```text
train: 70%
val:   20%
test:  10%
```

Do not split adjacent frames randomly if the footage is video-derived. Near-duplicate frames in train and val make the metrics look better than the model really is.

## Class Strategy

For the first hackathon/demo model:

```text
0: person
```

For HIT-UAV:

```text
0: person
1: bicycle
2: car
3: other_vehicle
```

If your demo goal is victim spotting, it is fine to train a person-only model first. For false-positive reduction, keep vehicle classes when training on HIT-UAV.

## Practical Notes

- Train thermal and RGB separately first.
- Use late fusion in the demo: compare thermal and RGB detections after inference, instead of building a custom RGB-T model immediately.
- Use `imgsz=960` or `1280` for small aerial people.
- Review low-confidence predictions manually; do not present the model as a final victim identifier.
