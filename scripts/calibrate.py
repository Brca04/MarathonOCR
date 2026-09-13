#!/usr/bin/env python3
"""Measure how well a recognizer's confidence predicts its correctness, and
pick the cascade threshold from that.

Calibration is a property of the whole pipeline — engine, preprocessing, crop
padding, upscale target — not a constant. Re-run this after changing any of
them; a stale threshold either spends money on crops the primary would have
got right, or accepts reads it would have got wrong.

    python scripts/calibrate.py --engine easyocr
    python scripts/calibrate.py --engine easyocr --target-fuzzy 0.99
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from marathon_ocr.crops import iter_crops, prepare_for_ocr  # noqa: E402
from marathon_ocr.dataset import Dataset  # noqa: E402
from marathon_ocr.metrics import levenshtein  # noqa: E402
from marathon_ocr.recognizers import build  # noqa: E402

BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
THRESHOLDS = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--annotations", default=str(ROOT / "archive" / "annotations.xml"))
    p.add_argument("--engine", default="easyocr")
    p.add_argument("--min-height", type=int, default=64)
    p.add_argument("--cpu", action="store_true")
    p.add_argument(
        "--target-fuzzy",
        type=float,
        default=0.98,
        help="lowest acceptable fuzzy@1 among ACCEPTED crops; the recommended "
        "threshold is the smallest one that still meets it, since a lower "
        "threshold defers fewer crops to the expensive fallback",
    )
    p.add_argument("--out", default=str(ROOT / "benchmark" / "results"))
    return p.parse_args()


def main() -> int:
    args = parse_args()

    dataset = Dataset.from_cvat(Path(args.annotations))
    prepared = [
        (s, prepare_for_ocr(s.image, args.min_height)) for s in iter_crops(dataset)
    ]

    kwargs: dict = {}
    if args.engine == "easyocr":
        kwargs["gpu"] = not args.cpu
    elif args.engine == "paddleocr":
        kwargs["use_gpu"] = not args.cpu

    recognizer = build(args.engine, **kwargs)
    recognizer.warmup()

    rows = []
    for spec, image in prepared:
        reading = recognizer.read(image)
        truth = spec.text or ""
        rows.append(
            {
                "truth": truth,
                "pred": reading.best,
                "conf": reading.confidence,
                "exact": reading.best == truth,
                "fuzzy1": levenshtein(reading.best, truth) <= 1,
            }
        )

    n = len(rows)
    print(f"\n{args.engine}: {n} crops\n")
    print(f"{'confidence':<14}{'n':>5}{'share':>8}{'exact':>9}{'fuzzy@1':>9}")
    for lo, hi in BUCKETS:
        sub = [r for r in rows if lo <= r["conf"] < hi]
        if not sub:
            continue
        print(
            f"{lo:.1f}-{min(hi, 1.0):<10.1f}{len(sub):>5}{len(sub) / n:>8.1%}"
            f"{sum(r['exact'] for r in sub) / len(sub):>8.1%}"
            f"{sum(r['fuzzy1'] for r in sub) / len(sub):>9.1%}"
        )

    print(f"\n{'threshold':<12}{'accepted':>10}{'exact':>9}{'fuzzy@1':>9}{'deferred':>10}")
    recommended = None
    for thr in THRESHOLDS:
        accepted = [r for r in rows if r["conf"] >= thr]
        if not accepted:
            continue
        fuzzy = sum(r["fuzzy1"] for r in accepted) / len(accepted)
        exact = sum(r["exact"] for r in accepted) / len(accepted)
        deferred = n - len(accepted)
        flag = ""
        if recommended is None and fuzzy >= args.target_fuzzy:
            recommended = thr
            flag = "  <-- recommended"
        print(
            f"{thr:<12.1f}{len(accepted) / n:>9.1%}{exact:>9.1%}"
            f"{fuzzy:>9.1%}{deferred:>10}{flag}"
        )

    if recommended is None:
        print(
            f"\nNo threshold reaches fuzzy@1 >= {args.target_fuzzy:.0%}. Either the "
            "target is too strict for this engine, or the fallback should handle "
            "everything."
        )
    else:
        deferred = sum(1 for r in rows if r["conf"] < recommended)
        print(
            f"\nRecommended threshold: {recommended}\n"
            f"  defers {deferred}/{n} crops ({deferred / n:.1%}) to the fallback.\n"
            f"  For a 20k-photo event at ~3 bibs/photo that is roughly "
            f"{round(60000 * deferred / n / 1000)}k fallback calls."
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"calibration_{args.engine}.json").write_text(
        json.dumps({"threshold": recommended, "rows": rows}, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
