#!/usr/bin/env python3
"""Baseline of the trained bib detector (best.pt) on the Željava photos.

Runs the real pipeline (YOLOBibDetector -> crop from the full-resolution photo
-> EasyOCR) over every photo, keeps every candidate reading at any confidence,
and scores the result against the hand-made answer key.

    python scripts/eval_zeljava.py                      # run (resumable) + score
    python scripts/eval_zeljava.py --limit 20           # quick smoke test
    python scripts/eval_zeljava.py --score-only         # re-score an existing run
    python scripts/eval_zeljava.py --imgsz 1920 --out runs/zeljava_bestpt_1920.jsonl

The run is written one photo per line to --out, so an interrupted run carries
on where it stopped. Nothing is downscaled before detection: YOLO looks at the
photo at --imgsz, and the OCR crops are cut from the original pixels.

Scoring, per photo-bib pair in the answer key, at each confidence threshold:
  found       the right number was read at or above the threshold
  low conf    the right number was read, but only below the threshold
  never seen  the right number was never read at any confidence
Precision counts every distinct (photo, number) read at or above the threshold,
with and without the start-list filter.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import re
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
THRESHOLDS = (0.0, 0.3, 0.5, 0.8)


def norm(bib: str) -> str:
    digits = "".join(ch for ch in str(bib) if ch.isdigit()).lstrip("0")
    return digits


def canon(name: str) -> str:
    """One spelling per photo: the key was written on a Mac (decomposed "Z" +
    caron) and Windows lists files composed ("Ž"), so compare NFC forms, and
    fall back to the photo number so "ŽeljavaPolumaraton - 7.jpg" and
    "0007.jpg" also meet."""
    name = unicodedata.normalize("NFC", name.strip())
    m = re.search(r"(\d+)\.[A-Za-z]+$", name)
    return str(int(m.group(1))) if m else name


def load_key(path: Path) -> dict[str, set[str]]:
    key: dict[str, set[str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            bibs = {norm(b) for b in (row.get("bib_numbers") or "").split(",") if norm(b)}
            key[canon(row["image_name"])] = bibs
    return key


def run(args, key: dict[str, set[str]]) -> None:
    from PIL import Image, ImageOps

    from marathon_ocr.detectors import YOLOBibDetector
    from marathon_ocr.pipeline import BibPipeline
    from marathon_ocr.recognizers import build

    weights = Path(args.weights)
    if not weights.exists():
        raise SystemExit(f"weights not found: {weights}")
    photos_dir = Path(args.photos)
    photos = sorted(p for p in photos_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if args.limit:
        photos = photos[: args.limit]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["file"])
    todo = [p for p in photos if p.name not in done]
    print(f"{len(photos)} photos, {len(done)} already done, {len(todo)} to run")
    if not todo:
        return

    detector = YOLOBibDetector(str(weights), conf=args.det_conf, imgsz=args.imgsz)
    recognizer = build("easyocr", gpu=not args.cpu)
    pipeline = BibPipeline(detector, recognizer, min_height=args.min_height, min_confidence=0.0)
    print(f"loading best.pt (imgsz {args.imgsz}, det-conf {args.det_conf}) + EasyOCR...")
    t0 = time.perf_counter()
    pipeline.warmup()
    print(f"ready in {time.perf_counter() - t0:.1f}s")

    started = time.perf_counter()
    with out.open("a", encoding="utf-8") as f:
        for i, path in enumerate(todo, 1):
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                t = time.perf_counter()
                result = pipeline.process(im)
                dt = time.perf_counter() - t
                row = {
                    "file": path.name,
                    "w": im.width,
                    "h": im.height,
                    "regions": result.regions_examined,
                    "seconds": round(dt, 3),
                    "hits": [
                        {
                            "text": h.text,
                            "conf": round(h.confidence, 4),
                            "det_conf": round(h.box.confidence, 4),
                            "bbox": [round(v, 1) for v in (h.box.x0, h.box.y0, h.box.x1, h.box.y1)],
                        }
                        for h in result.hits
                    ],
                }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 25 == 0 or i == len(todo):
                rate = (time.perf_counter() - started) / i
                print(f"  {i}/{len(todo)}  ({rate:.2f}s/photo, ~{rate * (len(todo) - i) / 60:.1f} min left)")


def score(args, key: dict[str, set[str]]) -> None:
    out = Path(args.out)
    if not out.exists():
        raise SystemExit(f"no run at {out}")
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    start = {norm(l) for l in Path(args.startlist).read_text().split() if norm(l)}

    # best confidence per (photo, number)
    reads: dict[str, dict[str, float]] = {}
    for r in rows:
        best: dict[str, float] = {}
        for h in r["hits"]:
            n = norm(h["text"])
            if n:
                best[n] = max(best.get(n, 0.0), h["conf"])
        reads[canon(r["file"])] = best

    scored = [f for f in reads if f in key]
    missing_key = [f for f in reads if f not in key]
    pairs = [(f, b) for f in scored for b in key[f]]
    single = sum(1 for _, b in pairs if len(b) == 1)
    zero_region_photos = sum(1 for r in rows if canon(r["file"]) in key and key[canon(r["file"])] and r["regions"] == 0)
    photos_with_bibs = sum(1 for f in scored if key[f])

    print()
    print(f"Run: {out}  ({len(rows)} photos, {len(scored)} in the answer key, {len(pairs)} photo-bib pairs)")
    if missing_key:
        print(f"  ! {len(missing_key)} photos not in the answer key (names differ?), e.g. {missing_key[:3]}")
    print(f"  single-digit bibs in the key: {single} pairs (the reader only accepts 2-6 digits, so these can't be found)")
    print(f"  photos with bibs where the detector found no region at all: {zero_region_photos} of {photos_with_bibs}")
    secs = [r["seconds"] for r in rows if "seconds" in r]
    if secs:
        print(f"  speed: {sum(secs) / len(secs):.2f}s per photo on average")
    print()

    header = f"{'threshold':>9} | {'found':>6} {'low conf':>8} {'never':>6} | {'precision':>9} {'reads':>6} | {'+ start list':>12} {'reads':>6}"
    print(header)
    print("-" * len(header))
    summary = []
    for t in THRESHOLDS:
        found = low = never = 0
        for f, b in pairs:
            c = reads[f].get(b)
            if c is None:
                never += 1
            elif c >= t:
                found += 1
            else:
                low += 1
        emitted = [(f, n) for f in scored for n, c in reads[f].items() if c >= t]
        correct = sum(1 for f, n in emitted if n in key[f])
        emitted_sl = [(f, n) for f, n in emitted if n in start]
        correct_sl = sum(1 for f, n in emitted_sl if n in key[f])
        P = correct / len(emitted) if emitted else 0
        Psl = correct_sl / len(emitted_sl) if emitted_sl else 0
        N = len(pairs) or 1
        print(
            f"{t:>9.1f} | {found / N:>6.1%} {low / N:>8.1%} {never / N:>6.1%} | {P:>9.1%} {len(emitted):>6} | {Psl:>12.1%} {len(emitted_sl):>6}"
        )
        summary.append(dict(threshold=t, found=found, low_conf=low, never=never, pairs=len(pairs),
                            precision=P, reads=len(emitted), precision_startlist=Psl, reads_startlist=len(emitted_sl)))
    print()
    print("found + low conf + never = 100% of pairs at each threshold; 'never' is the same on every row.")

    base = out.with_suffix("")
    Path(f"{base}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(f"{base}_misses.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "bib", "result", "best_conf", "what_was_read"])
        for fn, b in sorted(pairs):
            c = reads[fn].get(b)
            if c is None or c < 0.5:
                w.writerow([fn, b, "never" if c is None else "low_conf", "" if c is None else c,
                            " ".join(f"{n}:{v:.2f}" for n, v in sorted(reads[fn].items(), key=lambda x: -x[1]))])
    print(f"wrote {base}_summary.json and {base}_misses.csv")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--photos", default=str(ROOT / "src" / "slike"))
    p.add_argument("--key", default=str(ROOT / "data" / "answer_keys" / "zeljava-2026.csv"))
    p.add_argument("--startlist", default=str(ROOT / "data" / "answer_keys" / "zeljava-2026-startlist.txt"))
    p.add_argument("--weights", default=str(ROOT / "models" / "bib_detector" / "best.pt"))
    p.add_argument("--out", default=str(ROOT / "runs" / "zeljava_bestpt.jsonl"))
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--det-conf", type=float, default=0.25)
    p.add_argument("--min-height", type=int, default=64)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--score-only", action="store_true")
    args = p.parse_args()

    key = load_key(Path(args.key))
    if not args.score_only:
        run(args, key)
    score(args, key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
