#!/usr/bin/env python3
"""Build a self-contained demo gallery: annotated photos + a CSV listing each
photo's detected bib numbers. Meant for showing someone the pipeline working,
not for evaluation (see scripts/eval_end_to_end.py for that).

Usage:
    python scripts/make_demo_gallery.py --input archive/images --out demo_gallery
    python scripts/make_demo_gallery.py --input archive/images --out demo_gallery --limit 8
"""

from __future__ import annotations

import argparse
import csv
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

DEFAULT_BIB_WEIGHTS = ROOT / "models" / "bib_detector" / "best.pt"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def make_detector(kind: str, conf: float, weights: str | None):
    if kind == "whole":
        return WholeImageDetector()
    if kind == "person":
        return PersonDetector(conf=conf)
    if kind == "yolo-bib":
        weights_path = weights or str(DEFAULT_BIB_WEIGHTS)
        if not Path(weights_path).exists():
            raise SystemExit(f"bib detector weights not found at {weights_path}")
        return YOLOBibDetector(weights_path, conf=conf)
    return TorsoHeuristicDetector(PersonDetector(conf=conf))


def draw_boxes(image: Image.Image, hits) -> Image.Image:
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for hit in hits:
        b = hit.box
        draw.rectangle([b.x0, b.y0, b.x1, b.y1], outline="lime", width=4)
        label = f"{hit.text} ({hit.confidence:.2f})"
        draw.text((b.x0, max(0, b.y0 - 20)), label, fill="lime")
    return out


def iter_images(folder: Path):
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="folder of source photos")
    p.add_argument("--out", default="demo_gallery", help="output folder")
    p.add_argument("--detector", default="yolo-bib", choices=["torso", "person", "whole", "yolo-bib"])
    p.add_argument("--weights", default=None)
    p.add_argument("--det-conf", type=float, default=0.25)
    p.add_argument("--min-conf", type=float, default=0.3)
    p.add_argument("--min-height", type=int, default=64)
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="0 = all images")
    args = p.parse_args()

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        raise SystemExit(f"not a folder: {input_dir}")

    images = iter_images(input_dir)
    if args.limit:
        images = images[: args.limit]
    if not images:
        raise SystemExit(f"no images found in {input_dir}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    detector = make_detector(args.detector, args.det_conf, args.weights)
    recognizer = build("easyocr", gpu=not args.cpu)
    pipeline = BibPipeline(
        detector, recognizer, min_height=args.min_height, min_confidence=args.min_conf
    )

    print(f"loading {args.detector} detector + easyocr recognizer...")
    pipeline.warmup()
    print(f"processing {len(images)} photo(s) -> {out_dir}\n")

    rows = []
    for img_path in images:
        with Image.open(img_path) as img:
            img = img.convert("RGB")
            t0 = time.perf_counter()
            result = pipeline.process(img)
            elapsed = time.perf_counter() - t0

            hits = result.best_per_number()
            numbers = sorted((h.text for h in hits), key=int) if hits else []

            annotated = draw_boxes(img, hits)
            out_path = out_dir / img_path.name
            annotated.save(out_path)

            rows.append({"image": img_path.name, "bib_numbers": ", ".join(numbers)})
            print(f"{img_path.name:<20} ({elapsed:.2f}s) -> {numbers or '(none found)'}")

    csv_path = out_dir / "demo_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["image", "bib_numbers"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {len(rows)} annotated photos + {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
