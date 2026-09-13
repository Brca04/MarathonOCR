#!/usr/bin/env python3
"""Score the full pipeline on whole photos — the number that predicts the product.

``eval_recognizers.py`` measures recognition on perfect human-drawn crops. This
measures what happens when the detector has to find the bibs itself.

The headline metric is **photo recall**: for every (photo, bib) pair a human
annotated, did the pipeline surface that number anywhere in that photo? That is
literally "will the runner find their photo", and it is the only score that
maps onto the product.

Precision is reported alongside because false positives are not free — a
spurious bib puts a stranger's photo into someone's results, which is worse
than a miss.

    python scripts/eval_end_to_end.py --detector torso
    python scripts/eval_end_to_end.py --detector whole --detector torso
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from marathon_ocr.dataset import Dataset  # noqa: E402
from marathon_ocr.detectors import (  # noqa: E402
    PersonDetector,
    TorsoHeuristicDetector,
    WholeImageDetector,
    YOLOBibDetector,
)
from marathon_ocr.metrics import levenshtein  # noqa: E402
from marathon_ocr.pipeline import BibPipeline  # noqa: E402
from marathon_ocr.recognizers import build  # noqa: E402


def make_detector(kind: str, weights: str | None, conf: float):
    if kind == "whole":
        return WholeImageDetector()
    if kind == "person":
        return PersonDetector(conf=conf)
    if kind == "torso":
        return TorsoHeuristicDetector(PersonDetector(conf=conf))
    if kind == "yolo-bib":
        if not weights:
            raise SystemExit("--detector yolo-bib requires --weights path/to/best.pt")
        return YOLOBibDetector(weights, conf=conf)
    raise SystemExit(f"unknown detector {kind!r}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--annotations", default=str(ROOT / "archive" / "annotations.xml"))
    p.add_argument(
        "--detector",
        action="append",
        default=None,
        choices=["whole", "person", "torso", "yolo-bib"],
        help="repeatable; compares detectors on the same photos",
    )
    p.add_argument("--weights", default=None, help="for --detector yolo-bib")
    p.add_argument("--engine", default="easyocr")
    p.add_argument("--det-conf", type=float, default=0.25)
    p.add_argument("--min-height", type=int, default=64)
    p.add_argument(
        "--min-conf",
        type=float,
        default=0.0,
        help="drop recognizer candidates below this confidence (precision lever)",
    )
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "benchmark" / "results"))
    return p.parse_args()


def score(pipeline: BibPipeline, samples) -> dict:
    total_truth = 0
    found_exact = 0
    found_fuzzy = 0
    predicted_total = 0
    predicted_matching = 0
    regions = 0
    per_photo = []

    started = time.perf_counter()
    for sample in samples:
        with Image.open(sample.path) as img:
            result = pipeline.process(img.convert("RGB"))

        truth = [b.text for b in sample.legible_boxes]
        predicted = sorted(result.numbers)
        regions += result.regions_examined

        hits_exact = sum(1 for t in truth if t in predicted)
        hits_fuzzy = sum(
            1 for t in truth if any(levenshtein(t, p) <= 1 for p in predicted)
        )
        matching = sum(
            1 for p in predicted if any(levenshtein(t, p) <= 1 for t in truth)
        )

        total_truth += len(truth)
        found_exact += hits_exact
        found_fuzzy += hits_fuzzy
        predicted_total += len(predicted)
        predicted_matching += matching

        per_photo.append(
            {
                "image": sample.name,
                "truth": truth,
                "predicted": predicted,
                "recall_fuzzy": round(hits_fuzzy / len(truth), 3) if truth else None,
            }
        )

    elapsed = time.perf_counter() - started
    return {
        "photos": len(samples),
        "seconds": round(elapsed, 1),
        "s_per_photo": round(elapsed / max(len(samples), 1), 2),
        "regions_per_photo": round(regions / max(len(samples), 1), 1),
        "truth_bibs": total_truth,
        "predicted_bibs": predicted_total,
        "recall_exact": found_exact / total_truth if total_truth else 0.0,
        "recall_fuzzy1": found_fuzzy / total_truth if total_truth else 0.0,
        "precision_fuzzy1": (
            predicted_matching / predicted_total if predicted_total else 0.0
        ),
        "per_photo": per_photo,
    }


def main() -> int:
    args = parse_args()
    kinds = args.detector or ["torso"]

    dataset = Dataset.from_cvat(Path(args.annotations))
    samples = list(dataset)
    if args.limit:
        samples = samples[: args.limit]

    kwargs: dict = {}
    if args.engine == "easyocr":
        kwargs["gpu"] = not args.cpu
    elif args.engine == "paddleocr":
        kwargs["use_gpu"] = not args.cpu
    recognizer = build(args.engine, **kwargs)
    recognizer.warmup()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = {}
    for kind in kinds:
        detector = make_detector(kind, args.weights, args.det_conf)
        pipeline = BibPipeline(
            detector, recognizer, min_height=args.min_height, min_confidence=args.min_conf
        )
        pipeline.warmup()
        print(f"\nrunning {kind} + {args.engine} over {len(samples)} photos...")
        reports[kind] = score(pipeline, samples)
        (out_dir / f"e2e_{kind}.json").write_text(
            json.dumps(reports[kind], indent=2)
        )

    print(f"\n{'detector':<12}{'recall':>9}{'recall~1':>10}{'precision':>11}"
          f"{'pred/photo':>12}{'s/photo':>9}")
    for kind, r in reports.items():
        print(
            f"{kind:<12}{r['recall_exact']:>9.1%}{r['recall_fuzzy1']:>10.1%}"
            f"{r['precision_fuzzy1']:>11.1%}"
            f"{r['predicted_bibs'] / r['photos']:>12.1f}{r['s_per_photo']:>9.2f}"
        )

    print("\nrecall~1 is the product metric: did the runner's number appear "
          "somewhere in their photo, within edit distance 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
