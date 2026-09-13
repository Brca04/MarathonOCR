#!/usr/bin/env python3
"""Export ground-truth bib crops from the CVAT annotations.

Writes ``benchmark/crops/*.png`` plus ``benchmark/labels.csv``. Run this once,
then look at the crops. Seeing what the recognizer is actually being asked to
read is worth more than any single metric.

    python scripts/extract_crops.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from marathon_ocr.crops import export_benchmark_crops  # noqa: E402
from marathon_ocr.dataset import Dataset  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--annotations", default=str(ROOT / "archive" / "annotations.xml"))
    p.add_argument("--out", default=str(ROOT / "benchmark"))
    args = p.parse_args()

    dataset = Dataset.from_cvat(Path(args.annotations))
    print(json.dumps(dataset.summary(), indent=2))
    labels = export_benchmark_crops(dataset, args.out)
    print(f"\nwrote crops and labels -> {labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
