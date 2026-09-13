#!/usr/bin/env python3
"""Runnable prototype: point it at photo(s), get bib numbers back.

This is the thin CLI wrapper around the library the eval scripts already
exercise (``BibPipeline`` + ``TorsoHeuristicDetector`` + EasyOCR). Nothing new
is implemented here — it is the same detect -> crop -> upscale -> recognize
path, just runnable against your own photos instead of the eval set.

Usage:
    python scripts/run.py path/to/photo.jpg
    python scripts/run.py path/to/folder/            # every image in the folder
    python scripts/run.py photo.jpg --save-boxes out.jpg
    python scripts/run.py photo.jpg --detector whole  # skip person detection (control)
    python scripts/run.py photo.jpg --cpu             # force CPU
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from marathon_ocr.detectors import (  # noqa: E402
    PersonDetector,
    TorsoHeuristicDetector,
    WholeImageDetector,
    YOLOBibDetector,
)
from marathon_ocr.pipeline import BibPipeline  # noqa: E402
from marathon_ocr.recognizers import build  # noqa: E402

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_BIB_WEIGHTS = ROOT / "models" / "bib_detector" / "best.pt"


def make_detector(kind: str, conf: float, weights: str | None):
    if kind == "whole":
        return WholeImageDetector()
    if kind == "person":
        return PersonDetector(conf=conf)
    if kind == "yolo-bib":
        weights_path = weights or str(DEFAULT_BIB_WEIGHTS)
        if not Path(weights_path).exists():
            raise SystemExit(
                f"bib detector weights not found at {weights_path}. "
                "Train one with scripts/train_bib_detector.py or pass --weights."
            )
        return YOLOBibDetector(weights_path, conf=conf)
    return TorsoHeuristicDetector(PersonDetector(conf=conf))


def iter_images(path: Path):
    if path.is_dir():
        for p in sorted(path.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS:
                yield p
    else:
        yield path


def draw_boxes(image: Image.Image, hits) -> Image.Image:
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for hit in hits:
        b = hit.box
        draw.rectangle([b.x0, b.y0, b.x1, b.y1], outline="lime", width=3)
        label = f"{hit.text} ({hit.confidence:.2f})"
        draw.text((b.x0, max(0, b.y0 - 16)), label, fill="lime")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="image file or folder of images")
    p.add_argument(
        "--detector", default="yolo-bib", choices=["torso", "person", "whole", "yolo-bib"]
    )
    p.add_argument(
        "--weights",
        default=None,
        help="path to fine-tuned bib detector weights (for --detector yolo-bib; "
        f"defaults to {DEFAULT_BIB_WEIGHTS} if present)",
    )
    p.add_argument("--engine", default="easyocr")
    p.add_argument("--det-conf", type=float, default=0.25)
    p.add_argument("--min-height", type=int, default=64)
    p.add_argument(
        "--min-conf",
        type=float,
        default=0.3,
        help="drop recognizer candidates below this confidence "
        "(0.3 is the measured sweet spot: ~58%% precision at ~82%% recall "
        "on the eval set; use 0.0 to see everything)",
    )
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--save-boxes", help="write an annotated copy (single-image mode only)")
    args = p.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"not found: {input_path}")

    images = list(iter_images(input_path))
    if not images:
        raise SystemExit(f"no images found at {input_path}")
    if args.save_boxes and len(images) > 1:
        raise SystemExit("--save-boxes only supports a single image")

    kwargs = {"gpu": not args.cpu} if args.engine == "easyocr" else {}
    recognizer = build(args.engine, **kwargs)
    detector = make_detector(args.detector, args.det_conf, args.weights)
    pipeline = BibPipeline(
        detector, recognizer, min_height=args.min_height, min_confidence=args.min_conf
    )

    print(f"loading {args.detector} detector + {args.engine} recognizer...")
    t0 = time.perf_counter()
    pipeline.warmup()
    print(f"ready ({time.perf_counter() - t0:.1f}s)\n")

    for img_path in images:
        with Image.open(img_path) as img:
            img = img.convert("RGB")
            t0 = time.perf_counter()
            result = pipeline.process(img)
            elapsed = time.perf_counter() - t0

            hits = result.best_per_number()
            print(f"{img_path.name}  ({elapsed:.2f}s, {result.regions_examined} regions examined)")
            if hits:
                for hit in hits:
                    print(f"    {hit.text:<8} conf={hit.confidence:.2f}  h={hit.source_height:.0f}px")
            else:
                print("    (no bib numbers found)")

            if args.save_boxes:
                annotated = draw_boxes(img, hits)
                out_path = Path(args.save_boxes)
                annotated.save(out_path)
                print(f"    -> annotated image saved to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
