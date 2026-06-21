from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import yaml

IMAGE_EXTENSIONS = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a valid dataset YAML file.")
    return data


def normalize_names(names: object) -> Dict[int, str]:
    if isinstance(names, list):
        return {idx: str(name) for idx, name in enumerate(names)}
    if isinstance(names, dict):
        return {int(idx): str(name) for idx, name in names.items()}
    raise ValueError("Dataset YAML must contain names as a list or id:name mapping.")


def resolve_dataset_root(yaml_path: Path, data: dict) -> Path:
    root = Path(data.get("path", "."))
    if not root.is_absolute():
        root = yaml_path.parent / root
    return root.resolve()


def iter_images(path: Path) -> List[Path]:
    if not path.exists():
        return []
    if path.is_file():
        images = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line:
                images.append(Path(line))
        return images
    return sorted(
        file
        for file in path.rglob("*")
        if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
    )


def expected_label_path(root: Path, split_value: str, image_path: Path) -> Path:
    image_root = root / split_value
    try:
        relative = image_path.relative_to(image_root)
    except ValueError:
        relative = image_path.name
        return root / "labels" / Path(relative).with_suffix(".txt")

    parts = list(relative.parts)
    if split_value.startswith("images/") and len(parts) >= 1:
        split = split_value.split("/", 1)[1]
        return root / "labels" / split / Path(*parts).with_suffix(".txt")
    return root / "labels" / Path(*parts).with_suffix(".txt")


def validate_label_file(path: Path, class_count: int) -> Tuple[int, int]:
    if not path.exists():
        return 0, 1

    valid_rows = 0
    invalid_rows = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            invalid_rows += 1
            continue
        try:
            class_id = int(float(parts[0]))
            coords = [float(value) for value in parts[1:]]
        except ValueError:
            invalid_rows += 1
            continue
        if class_id < 0 or class_id >= class_count:
            invalid_rows += 1
            continue
        if any(value < 0.0 or value > 1.0 for value in coords):
            invalid_rows += 1
            continue
        valid_rows += 1
    return valid_rows, invalid_rows


def check_dataset(data_yaml: Path) -> int:
    data = load_yaml(data_yaml)
    names = normalize_names(data.get("names"))
    root = resolve_dataset_root(data_yaml, data)

    print(f"Dataset YAML: {data_yaml}")
    print(f"Dataset root: {root}")
    print(f"Classes: {names}")

    failures = 0
    for split in ("train", "val", "test"):
        split_value = data.get(split)
        if not split_value:
            if split != "test":
                print(f"[{split}] missing from YAML")
                failures += 1
            continue

        split_path = Path(split_value)
        if not split_path.is_absolute():
            split_path = root / split_path

        images = iter_images(split_path)
        if not images:
            print(f"[{split}] no images found at {split_path}")
            failures += 1
            continue

        label_files = [expected_label_path(root, str(split_value), image) for image in images]
        missing_labels = 0
        valid_rows = 0
        invalid_rows = 0
        for label_file in label_files:
            valid, invalid = validate_label_file(label_file, len(names))
            valid_rows += valid
            invalid_rows += invalid
            if invalid and not label_file.exists():
                missing_labels += 1

        print(
            f"[{split}] images={len(images)} labels={len(label_files) - missing_labels} "
            f"missing_labels={missing_labels} valid_boxes={valid_rows} invalid_rows={invalid_rows}"
        )
        if missing_labels or invalid_rows:
            failures += 1

    if failures:
        print("Dataset check failed.")
        return 1
    print("Dataset check passed.")
    return 0


def write_dataset_yaml(output: Path, root: Path, names: Iterable[str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    name_map = {idx: name for idx, name in enumerate(names)}
    data = {
        "path": str(root),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": name_map,
    }
    with output.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, sort_keys=False)
    print(f"Wrote {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YOLO dataset helpers for SAR demo data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Validate image/label counts and YOLO label rows.")
    check.add_argument("--data", required=True, type=Path, help="Path to dataset YAML.")

    make_yaml = subparsers.add_parser("make-yaml", help="Create a dataset YAML for an existing YOLO tree.")
    make_yaml.add_argument("--root", required=True, type=Path, help="Dataset root directory.")
    make_yaml.add_argument("--output", required=True, type=Path, help="YAML file to write.")
    make_yaml.add_argument("--names", required=True, nargs="+", help="Class names in id order.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "check":
        return check_dataset(args.data)
    if args.command == "make-yaml":
        write_dataset_yaml(args.output, args.root, args.names)
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
