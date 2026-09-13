#!/usr/bin/env python3
"""Fine-tune a single-class YOLO11 bib detector on the Roboflow dataset in
``src/bib number labeling.v14i.yolov11`` and drop the weights where
``YOLOBibDetector`` expects them.

The dataset ships with a relative-path ``data.yaml`` (``../train/images`` etc.)
which only resolves correctly if you run from inside the dataset folder. This
script writes an absolute-path copy next to it so training works from the repo
root, matching how every other script in this project is invoked.

Usage:
    python scripts/train_bib_detector.py                  # sensible defaults
    python scripts/train_bib_detector.py --epochs 50 --model yolo11s.pt
    python scripts/train_bib_detector.py --imgsz 1280 --batch 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "src" / "bib number labeling.v14i.yolov11"
BEST_WEIGHTS_DEST = ROOT / "models" / "bib_detector" / "best.pt"


def write_absolute_yaml() -> Path:
    """Rewrite data.yaml with absolute paths so training works from any cwd."""
    src_yaml = DATASET_DIR / "data.yaml"
    if not src_yaml.exists():
        raise SystemExit(f"dataset not found: {src_yaml}")

    with src_yaml.open() as fh:
        cfg = yaml.safe_load(fh)

    for split in ("train", "val", "test"):
        if split in cfg:
            # The shipped yaml uses ../train/images etc., written as if the
            # yaml lived one directory deeper than it does. The actual images
            # are directly under DATASET_DIR/<split>/images, so strip any
            # leading ../ and resolve against DATASET_DIR itself.
            rel = Path(cfg[split])
            parts = [p for p in rel.parts if p != ".."]
            resolved = (DATASET_DIR / Path(*parts)).resolve()
            cfg[split] = str(resolved)

    out_yaml = DATASET_DIR / "data.absolute.yaml"
    with out_yaml.open("w") as fh:
        yaml.safe_dump(cfg, fh)
    return out_yaml


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--model",
        default="yolo11n.pt",
        help="base checkpoint to fine-tune (yolo11n/s/m.pt); nano is fastest, "
        "small is more accurate if you have the time",
    )
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--imgsz", type=int, default=960)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--patience", type=int, default=15, help="early stopping")
    p.add_argument("--device", default="0", help="cuda device id, or 'cpu'")
    p.add_argument("--name", default="bib_detector")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    data_yaml = write_absolute_yaml()
    print(f"dataset config: {data_yaml}")

    from ultralytics import YOLO

    model = YOLO(args.model)
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        device=args.device,
        project=str(ROOT / "runs" / "bib_detector"),
        name=args.name,
        exist_ok=True,
    )

    # ultralytics writes best.pt under <project>/<name>/weights/best.pt
    run_dir = Path(results.save_dir)
    best = run_dir / "weights" / "best.pt"
    if not best.exists():
        print(f"warning: expected weights at {best}, not found", file=sys.stderr)
        return 1

    BEST_WEIGHTS_DEST.parent.mkdir(parents=True, exist_ok=True)
    BEST_WEIGHTS_DEST.write_bytes(best.read_bytes())
    print(f"\nbest weights copied to {BEST_WEIGHTS_DEST}")
    print(
        f"use with: python scripts/run.py photo.jpg --detector yolo-bib "
        f"--weights {BEST_WEIGHTS_DEST}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
