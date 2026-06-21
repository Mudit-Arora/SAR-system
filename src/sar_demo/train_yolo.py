from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fine-tune a YOLO detector for SAR drone footage.")
    parser.add_argument("--data", required=True, type=Path, help="Ultralytics dataset YAML.")
    parser.add_argument("--model", default="yolo11s.pt", help="Base model, e.g. yolo11s.pt or yolo11n.pt.")
    parser.add_argument("--epochs", default=80, type=int)
    parser.add_argument("--imgsz", default=960, type=int)
    parser.add_argument("--batch", default=8, type=int)
    parser.add_argument("--device", default=None, help="CUDA/MPS/CPU device, e.g. 0, cpu, or mps.")
    parser.add_argument("--workers", default=4, type=int)
    parser.add_argument("--patience", default=20, type=int)
    parser.add_argument("--project", default="runs/detect")
    parser.add_argument("--name", default="sar_yolo11s")
    parser.add_argument("--cache", action="store_true", help="Cache images during training.")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted Ultralytics run.")
    parser.add_argument("--export-format", default=None, help="Optional export format after training, e.g. onnx.")
    return parser


def import_yolo():
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Ultralytics is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    return YOLO


def train(args: argparse.Namespace) -> None:
    if not args.data.exists():
        raise SystemExit(f"Dataset YAML not found: {args.data}")

    YOLO = import_yolo()
    model = YOLO(args.model)

    train_kwargs: Dict[str, Any] = {
        "data": str(args.data),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "workers": args.workers,
        "patience": args.patience,
        "project": args.project,
        "name": args.name,
        "cache": args.cache,
        "resume": args.resume,
        "exist_ok": True,
    }
    if args.device:
        train_kwargs["device"] = args.device

    print("Starting YOLO training with:")
    for key, value in train_kwargs.items():
        print(f"  {key}: {value}")
    print(f"  model: {args.model}")

    results = model.train(**train_kwargs)
    print(f"Training complete: {results}")

    if args.export_format:
        print(f"Exporting best model as {args.export_format}...")
        model.export(format=args.export_format)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    train(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
