#!/usr/bin/env python3
"""Resume the bib detector training run interrupted by the power loss.

Ultralytics' resume=True restores optimizer state, epoch count, and LR
schedule from the checkpoint's embedded training args -- this continues the
exact same run rather than restarting, so results.csv picks up at epoch 12.
"""

from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
LAST_CKPT = ROOT / "runs" / "bib_detector" / "bib_detector" / "weights" / "last.pt"
BEST_WEIGHTS_DEST = ROOT / "models" / "bib_detector" / "best.pt"


def main() -> int:
    if not LAST_CKPT.exists():
        raise SystemExit(f"checkpoint not found: {LAST_CKPT}")

    model = YOLO(str(LAST_CKPT))
    results = model.train(resume=True)

    run_dir = Path(results.save_dir)
    best = run_dir / "weights" / "best.pt"
    if not best.exists():
        print(f"warning: expected weights at {best}, not found")
        return 1

    BEST_WEIGHTS_DEST.parent.mkdir(parents=True, exist_ok=True)
    BEST_WEIGHTS_DEST.write_bytes(best.read_bytes())
    print(f"\nbest weights copied to {BEST_WEIGHTS_DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
