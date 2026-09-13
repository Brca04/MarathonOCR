#!/usr/bin/env python3
"""Score one or more recognizers on ground-truth crops.

This is the measurement that decides your recognizer. It removes detection
error entirely — every crop is a perfect, deskewed, human-drawn box — so the
numbers it produces are an **upper bound** on end-to-end performance. If an
engine cannot read these, nothing downstream will rescue it.

    python scripts/eval_recognizers.py --engines easyocr paddleocr
    python scripts/eval_recognizers.py --engines vlm --limit 40
    python scripts/eval_recognizers.py --engines easyocr --cpu

Results are written to ``benchmark/results/<engine>.json`` so runs accumulate
and you can diff a change against the last one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from marathon_ocr.crops import iter_crops, prepare_for_ocr  # noqa: E402
from marathon_ocr.dataset import Dataset  # noqa: E402
from marathon_ocr.metrics import Prediction, ScoreBoard  # noqa: E402
from marathon_ocr.recognizers import build  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--annotations",
        default=str(ROOT / "archive" / "annotations.xml"),
        help="CVAT annotations.xml defining the evaluation set",
    )
    p.add_argument(
        "--engines",
        nargs="+",
        default=["easyocr"],
        help="recognizers to score: easyocr paddleocr trocr vlm",
    )
    p.add_argument("--limit", type=int, default=0, help="score only the first N crops")
    p.add_argument(
        "--min-height",
        type=int,
        default=64,
        help="upscale crops to at least this pixel height before recognition",
    )
    p.add_argument("--cpu", action="store_true", help="force CPU inference")
    p.add_argument(
        "--out",
        default=str(ROOT / "benchmark" / "results"),
        help="directory for per-engine JSON results",
    )
    return p.parse_args()


def load_crops(annotations: Path, min_height: int, limit: int):
    dataset = Dataset.from_cvat(annotations)
    print(json.dumps(dataset.summary(), indent=2), file=sys.stderr)

    specs = list(iter_crops(dataset))
    if limit:
        specs = specs[:limit]

    prepared = [(s, prepare_for_ocr(s.image, min_height)) for s in specs]
    print(f"\nprepared {len(prepared)} crops\n", file=sys.stderr)
    return prepared


def score(engine_name: str, prepared, use_gpu: bool) -> ScoreBoard:
    kwargs: dict = {}
    if engine_name == "easyocr":
        kwargs["gpu"] = use_gpu
    elif engine_name == "paddleocr":
        kwargs["use_gpu"] = use_gpu

    recognizer = build(engine_name, **kwargs)
    recognizer.warmup()  # keep model loading out of the timing

    board = ScoreBoard(name=engine_name)
    started = time.perf_counter()
    for spec, image in prepared:
        reading = recognizer.read(image)
        board.add(
            Prediction(
                key=spec.key,
                truth=spec.text or "",
                predicted=reading.best,
                confidence=reading.confidence,
                original_height=spec.original_height,
            )
        )
    board.elapsed_s = time.perf_counter() - started
    return board


def main() -> int:
    args = parse_args()
    annotations = Path(args.annotations)
    if not annotations.exists():
        print(f"annotations not found: {annotations}", file=sys.stderr)
        return 1

    prepared = load_crops(annotations, args.min_height, args.limit)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    boards = []
    for engine in args.engines:
        try:
            board = score(engine, prepared, use_gpu=not args.cpu)
        except ImportError as exc:
            print(f"[skip] {engine}: {exc}", file=sys.stderr)
            continue
        except Exception as exc:  # noqa: BLE001 - one bad engine must not end the run
            print(f"[fail] {engine}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        boards.append(board)
        print("\n" + board.format_table())
        print("\n  worst reads:")
        for p in board.worst(10):
            print(f"    {p.key:<16} truth={p.truth:<8} got={p.predicted or '-':<8} "
                  f"h={p.original_height:.0f}px")

        (out_dir / f"{engine}.json").write_text(
            json.dumps(
                {
                    "report": board.report(),
                    "predictions": [
                        {
                            "key": p.key,
                            "truth": p.truth,
                            "predicted": p.predicted,
                            "confidence": p.confidence,
                            "height": p.original_height,
                        }
                        for p in board.predictions
                    ],
                },
                indent=2,
            )
        )

    if len(boards) > 1:
        print("\n\n=== comparison (all crops) ===")
        print(f"{'engine':<14}{'exact':>9}{'fuzzy@1':>10}{'CER':>8}{'ms/crop':>10}")
        for b in boards:
            r = b.report()
            s = r["buckets"]["all"]
            print(
                f"{b.name:<14}{s['exact']:>8.1%}{s['fuzzy1']:>10.1%}"
                f"{s['cer']:>8.3f}{r['per_crop_ms']:>10.1f}"
            )

    return 0 if boards else 1


if __name__ == "__main__":
    raise SystemExit(main())
