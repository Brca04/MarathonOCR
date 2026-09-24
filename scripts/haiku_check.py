#!/usr/bin/env python3
"""Step 2 of the review chain: Claude Haiku double-checks the unsure bib reads.

    local OCR  ->  Haiku (this script)  ->  you, in review_app.py

For every runner in every photo it looks at the local model's best read. Reads
at or above --confident (0.8 by default) are accepted as they are. Everything
else - low-confidence reads and runners where no bib was read at all - goes to
Haiku, and the two opinions are combined into a verdict. The result is written
next to the photos as .marathon_ocr_haiku.json, which review_app.py picks up to
put disagreements first and pre-fill its suggestions.

Usage (repo root, with ANTHROPIC_API_KEY in .env or the environment):

    python scripts/haiku_check.py --photos src/slike --ocr _transfer/ocr_all.jsonl \
        --meta _transfer/meta.csv

    --dry-run        decide what would be sent and print the estimated cost
    --workers 8      parallel Haiku calls
    --limit 20       only the first N photos (try it on a sample first)

Re-running is safe: photos already checked are skipped.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from marathon_ocr.verify import DEFAULT_MODEL, HaikuVerifier, judge  # noqa: E402

OUT_NAME = ".marathon_ocr_haiku.json"
# Haiku 4.5 list price, USD per million tokens (input, output).
PRICE = (1.0, 5.0)


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    import os
    for line in env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def person_boxes(yolo, im: Image.Image, device: str) -> list[tuple[list[float], float]]:
    out = []
    for r in yolo.predict(im, classes=[0], conf=0.3, device=device, verbose=False):
        for b in r.boxes:
            out.append(([float(v) for v in b.xyxy[0]], float(b.conf[0])))
    return out


def torso(box: list[float], w: int, h: int) -> tuple[int, int, int, int]:
    """The band a bib is pinned to, with a little margin - same as the OCR step."""
    x0, y0, x1, y1 = box
    ph, pw = y1 - y0, x1 - x0
    return (max(0, round(x0 - 0.05 * pw)), max(0, round(y0 + 0.10 * ph)),
            min(w, round(x1 + 0.05 * pw)), min(h, round(y0 + 0.95 * ph)))


def hits_in(box: tuple[int, int, int, int], hits: list[dict]) -> list[tuple[str, float]]:
    x0, y0, x1, y1 = box
    out = []
    for h in hits:
        cx = (h["bbox"][0] + h["bbox"][2]) / 2
        cy = (h["bbox"][1] + h["bbox"][3]) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            out.append((h["text"], h["conf"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photos", required=True, help="folder with the original photos")
    ap.add_argument("--ocr", required=True, help="OCR results (.jsonl) from the local model")
    ap.add_argument("--meta", help="CSV with file,original_name when OCR used renamed files")
    ap.add_argument("--confident", type=float, default=0.8)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-whole-photo", action="store_true",
                    help="skip the extra whole-photo Haiku look (one call per photo)")
    args = ap.parse_args()
    load_env()

    photos = Path(args.photos)
    # A dry run never touches the real results file, so it can't mark photos done.
    out_path = photos / (OUT_NAME + (".dryrun" if args.dry_run else ""))
    results: dict = {} if args.dry_run or not out_path.exists() else json.loads(out_path.read_text())

    names = {}
    if args.meta:
        names = {r["file"]: r["original_name"] for r in csv.DictReader(open(args.meta, encoding="utf-8"))}
    ocr = {}
    for line in open(args.ocr, encoding="utf-8"):
        d = json.loads(line)
        ocr[names.get(d["file"], d["file"])] = d

    # Photos where a Haiku call failed (rate limit, network) are retried.
    retry = {n for n, r in results.items()
             if any(p["verdict"] == "error" for p in r["persons"])
             or (r.get("whole_photo") or {}).get("error")}
    todo = [n for n in sorted(ocr) if (n not in results or n in retry) and (photos / n).exists()]
    if args.limit:
        todo = todo[: args.limit]
    missing = [n for n in ocr if not (photos / n).exists()]
    if missing:
        print(f"! {len(missing)} OCR entries have no matching photo (first: {missing[0]})")
    print(f"{len(results)} already checked, {len(todo)} to go  (model {args.model})")
    if not todo:
        return 0

    import torch
    from ultralytics import YOLO

    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    yolo = YOLO("yolo11n.pt")
    haiku = None if args.dry_run else HaikuVerifier(model=args.model)

    spent_in = spent_out = sent = 0
    t0 = time.time()
    pool = ThreadPoolExecutor(max_workers=args.workers)

    for i, name in enumerate(todo, 1):
        d = ocr[name]
        im = ImageOps.exif_transpose(Image.open(photos / name)).convert("RGB")
        # OCR coordinates are in the (≤2000 px) frame it worked on.
        scale = max(im.size) / max(d["w"], d["h"]) if max(d["w"], d["h"]) else 1.0
        work = im if scale <= 1.01 else im.resize((d["w"], d["h"]), Image.LANCZOS)

        persons = []
        for box, pconf in person_boxes(yolo, work, device):
            if box[3] - box[1] < 80:        # too far away to carry a readable bib
                continue
            tb = torso(box, work.width, work.height)
            cands = hits_in(tb, d["hits"])
            best = max((c for _, c in cands), default=0.0)
            persons.append(dict(box=[round(v) for v in tb], ocr=cands,
                                unsure=best < args.confident))

        # Hits the person detector didn't cover still count (e.g. cropped runners).
        covered = {(t, c) for p in persons for t, c in p["ocr"]}
        for h in d["hits"]:
            if (h["text"], h["conf"]) not in covered and h["conf"] >= args.confident:
                persons.append(dict(box=h["bbox"], ocr=[(h["text"], h["conf"])], unsure=False))

        futures = {}
        for k, p in enumerate(persons):
            if p["unsure"] and haiku is not None:
                crop = work.crop(tuple(p["box"]))
                hint = [t for t, _ in sorted(p["ocr"], key=lambda c: -c[1])[:3]]
                futures[k] = pool.submit(haiku.read, crop, hint)

        entry_persons, numbers, needs = [], [], 0
        for k, p in enumerate(persons):
            hr = futures[k].result() if k in futures else None
            if hr is not None:
                sent += 1
                spent_in += hr.input_tokens
                spent_out += hr.output_tokens
            v = judge(p["ocr"], hr, args.confident)
            needs += v.needs_human
            for n in v.numbers:
                if n not in numbers:
                    numbers.append(n)
            entry_persons.append(dict(
                box=p["box"], ocr=p["ocr"], unsure=p["unsure"], verdict=v.kind, needs_human=v.needs_human,
                haiku=None if hr is None else dict(numbers=hr.numbers, clarity=hr.clarity,
                                                   note=hr.note, error=hr.error)))

        # Whole-photo pass: one more look at the full frame, for runners the
        # person detector missed or cropped wrong. Anything it reads that the
        # per-runner step did not is added as its own entry, flagged for you.
        whole = None
        if haiku is not None and not args.no_whole_photo:
            whole = haiku.read_whole(work, numbers)
            sent += 1
            spent_in += whole.input_tokens
            spent_out += whole.output_tokens
            seen_by_model = {t for p in persons for t, _ in p["ocr"]} | {h["text"] for h in d["hits"]}
            for n in whole.numbers:
                if n in numbers:
                    continue
                clear = whole.clarity.get(n) == "clear"
                if clear:
                    numbers.append(n)
                needs += 1
                entry_persons.append(dict(
                    box=[0, 0, work.width, work.height],
                    ocr=[(t, c) for t, c in ((h["text"], h["conf"]) for h in d["hits"]) if t == n],
                    unsure=True, verdict="whole_only", needs_human=True,
                    haiku=dict(numbers=[n], clarity={n: whole.clarity.get(n)}, note=whole.note,
                               error=None, model_saw_it=n in seen_by_model)))

        results[name] = dict(numbers=numbers, needs_human=needs, persons=entry_persons,
                             sent_to_haiku=len(futures) + (1 if whole else 0),
                             whole_photo=None if whole is None else dict(
                                 numbers=whole.numbers, clarity=whole.clarity, error=whole.error))
        if i % 10 == 0 or i == len(todo):
            out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
            cost = spent_in / 1e6 * PRICE[0] + spent_out / 1e6 * PRICE[1]
            print(f"{i}/{len(todo)}  sent {sent} crops  ~${cost:.2f}  {time.time() - t0:.0f}s", flush=True)

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    unsure = sum(p["unsure"] for r in results.values() for p in r["persons"])
    flagged = sum(1 for r in results.values() if r["needs_human"])
    if args.dry_run:
        est = unsure * (1100 / 1e6 * PRICE[0] + 60 / 1e6 * PRICE[1])
        if not args.no_whole_photo:
            est += len(results) * (2100 / 1e6 * PRICE[0] + 120 / 1e6 * PRICE[1])
        print(f"dry run: {unsure} crops + {0 if args.no_whole_photo else len(results)} whole photos "
              f"would go to Haiku, est. ${est:.2f}")
    print(f"done. {flagged} of {len(results)} photos need you  ->  {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
