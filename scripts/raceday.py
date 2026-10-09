#!/usr/bin/env python3
"""Race day: photos in, searchable site out, batch by batch.

Layout: one root folder, one sub-folder per batch as it arrives, e.g.

    D:\\ZG26\\
        01_start_ana\\        *.jpg
        02_10k_marko\\        *.jpg
        03_finish_ana\\       *.jpg

Any folder under the root that directly holds photos is a batch. A batch can
arrive while another is being processed; just run the command again.

    python scripts/raceday.py scan    --root D:\\ZG26      # recognise new photos (GPU)
    (optional) review a batch in the review app: streamlit run review_app.py -- --folder D:\\ZG26\\02_10k_marko
    python scripts/raceday.py publish --root D:\\ZG26      # upload + tag + rebuild the site
    python scripts/raceday.py status  --root D:\\ZG26      # what is where

`scan` runs the old detector (best.pt) and the fine-tuned one (best_v3.pt)
together, merges their boxes, reads every box with EasyOCR, and writes in each
batch folder:
    .raceday_reads.jsonl            every read, one photo per line (resume point)
    .marathon_ocr_suggestions.json  what the review app pre-fills and sorts by

`publish` collects every batch: numbers you confirmed in the review app win;
photos nobody reviewed take the confident reads (on the start list, if given).
Then it runs the web scripts: publish-photos (resize + upload to R2),
import-bibs (tags), publish-event (export + rebuild via the deploy hook).

Everything is safe to re-run: done photos are skipped, uploads are skipped,
tags are replaced per photo.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
READS = ".raceday_reads.jsonl"
SUGGESTIONS = ".marathon_ocr_suggestions.json"
REVIEW = ".marathon_ocr_review.json"
WEIGHTS = [ROOT / "models" / "bib_detector" / "best.pt", ROOT / "models" / "bib_detector" / "best_v3.pt"]


# --------------------------------------------------------------------------- batches

def batches(root: Path) -> list[Path]:
    """Every folder under root (root included) that directly holds photos."""
    out = []
    for d in [root, *sorted(p for p in root.rglob("*") if p.is_dir())]:
        if any(part.startswith(".") or part.startswith("_") for part in d.relative_to(root).parts):
            continue
        if any(f.suffix.lower() in IMAGE_EXTS and not f.name.startswith(".") for f in d.iterdir()):
            out.append(d)
    return out


def photos_in(batch: Path) -> list[Path]:
    return sorted(f for f in batch.iterdir() if f.suffix.lower() in IMAGE_EXTS and not f.name.startswith("."))


def key_of(root: Path, photo: Path) -> str:
    """The photo's name everywhere else (R2, database): path under root, forward slashes.
    publish-photos.mjs names files exactly this way."""
    return photo.relative_to(root).as_posix()


def load_reads(batch: Path) -> dict[str, dict]:
    p = batch / READS
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["file"]] = r
    return out


def load_start_list(path: str | None) -> set[str] | None:
    if not path:
        return None
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    if p.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        col = next((c for c in (rows[0].keys() if rows else []) if c.strip().lower() in
                    ("bib", "startni_broj", "startni broj", "broj", "start_no", "number")), None)
        vals = [r[col] for r in rows] if col else []
    else:
        vals = text.split()
    out = {"".join(ch for ch in v if ch.isdigit()).lstrip("0") for v in vals}
    out.discard("")
    print(f"start list: {len(out)} bibs from {p}")
    return out


def norm(t: str) -> str:
    return "".join(ch for ch in t if ch.isdigit()).lstrip("0")


# --------------------------------------------------------------------------- recognition

class CombinedDetector:
    """Union of several YOLO bib detectors; overlapping boxes merged (IoU >= 0.5)."""

    name = "combined"

    def __init__(self, weights: list[Path], conf: float, imgsz: int):
        from marathon_ocr.detectors import YOLOBibDetector

        self.parts = [YOLOBibDetector(str(w), conf=conf, imgsz=imgsz) for w in weights]

    def warmup(self) -> None:
        for p in self.parts:
            p.warmup()

    def detect(self, image):
        boxes = [b for p in self.parts for b in p.detect(image)]
        boxes.sort(key=lambda b: -b.confidence)
        keep = []
        for b in boxes:
            if all(_iou(b, k) < 0.5 for k in keep):
                keep.append(b)
        return keep


def _iou(a, b) -> float:
    x0, y0, x1, y1 = max(a.x0, b.x0), max(a.y0, b.y0), min(a.x1, b.x1), min(a.y1, b.y1)
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a.width * a.height + b.width * b.height - inter
    return inter / union if union else 0.0


def suggestions_for(rows: dict[str, dict], start: set[str] | None, prefill_at: float) -> dict:
    """Review-app format (same as scripts/make_suggestions.py), keyed by bare file name."""
    out = {}
    for name, r in rows.items():
        best: dict[str, dict] = {}
        for h in r["hits"]:
            t = norm(h["text"])
            if t and (t not in best or h["conf"] > best[t]["conf"]):
                best[t] = h
        persons, numbers, unsure = [], [], 0
        for t, h in sorted(best.items(), key=lambda kv: -kv[1]["conf"]):
            if h["conf"] < 0.1:
                continue
            real = (t in start) if start is not None else len(t) >= 2
            take = real and h["conf"] >= prefill_at
            if take:
                numbers.append(t)
            elif h["conf"] >= 0.3:
                unsure += 1  # weak junk reads (texture, logos) do not push a photo up the queue
            persons.append(dict(box=h["bbox"], ocr=[[t, h["conf"]]], unsure=not take,
                                verdict="confident" if take else "model_only",
                                needs_human=not take, haiku=None, on_start_list=real))
        # Photos with something unsure come first in the review app.
        out[Path(name).name] = dict(numbers=numbers, needs_human=unsure, persons=persons, source="raceday")
    return out


def cmd_scan(args) -> int:
    from PIL import Image, ImageOps

    from marathon_ocr.pipeline import BibPipeline
    from marathon_ocr.recognizers import build

    root = Path(args.root).resolve()
    weights = [w for w in WEIGHTS if w.exists()]
    if not weights:
        raise SystemExit(f"no detector weights found in {WEIGHTS[0].parent}")
    if len(weights) < len(WEIGHTS):
        print(f"! only {', '.join(w.name for w in weights)} found; running with that")
    start = load_start_list(args.start_list)

    todo: list[tuple[Path, Path]] = []
    per_batch: dict[Path, dict] = {}
    for b in batches(root):
        done = load_reads(b)
        per_batch[b] = done
        todo += [(b, p) for p in photos_in(b) if p.name not in done]
    total = sum(len(photos_in(b)) for b in per_batch)
    print(f"{len(per_batch)} batch(es), {total} photos, {len(todo)} new")

    if todo:
        detector = CombinedDetector(weights, conf=args.det_conf, imgsz=args.imgsz)
        pipe = BibPipeline(detector, build("easyocr", gpu=not args.cpu), min_height=64,
                           expand=args.expand, min_confidence=0.0)
        pipe.warmup()
        print(f"models: {', '.join(w.name for w in weights)}  (imgsz {args.imgsz}, det-conf {args.det_conf})")

        # Decode the next photos on a second thread while the GPU works.
        q: queue.Queue = queue.Queue(maxsize=8)

        def loader():
            for b, p in todo:
                try:
                    with Image.open(p) as im:
                        q.put((b, p, ImageOps.exif_transpose(im).convert("RGB"), None))
                except Exception as e:  # unreadable file: record and move on
                    q.put((b, p, None, str(e)))
            q.put(None)

        threading.Thread(target=loader, daemon=True).start()
        handles = {}
        t0, n, failed = time.perf_counter(), 0, 0
        try:
            while (item := q.get()) is not None:
                b, p, im, err = item
                f = handles.get(b) or handles.setdefault(b, (b / READS).open("a", encoding="utf-8"))
                row = {"file": p.name, "hits": [], "regions": 0}
                if err:
                    row["error"] = err
                    failed += 1
                else:
                    res = pipe.process(im)
                    row.update(w=im.width, h=im.height, regions=res.regions_examined, hits=[
                        {"text": h.text, "conf": round(h.confidence, 4), "det_conf": round(h.box.confidence, 4),
                         "bbox": [round(v, 1) for v in (h.box.x0, h.box.y0, h.box.x1, h.box.y1)]}
                        for h in res.hits])
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                per_batch[b][p.name] = row
                n += 1
                if n % 50 == 0 or n == len(todo):
                    rate = (time.perf_counter() - t0) / n
                    print(f"  {n}/{len(todo)}  {rate:.2f}s/photo  ~{rate * (len(todo) - n) / 60:.0f} min left", flush=True)
        finally:
            for f in handles.values():
                f.close()
        if failed:
            print(f"! {failed} photo(s) could not be opened (marked, skipped)")

    for b, rows in per_batch.items():
        sug = suggestions_for(rows, start, args.prefill_at)
        (b / SUGGESTIONS).write_text(json.dumps(sug, ensure_ascii=False, indent=1), encoding="utf-8")
    print("suggestions written for the review app. Next: review (optional), then  raceday.py publish")
    return 0


# --------------------------------------------------------------------------- export + publish

def export(root: Path, start: set[str] | None, prefill_at: float) -> tuple[Path, Path, dict]:
    rows_csv, review_all = [], {}
    stats = {"photos": 0, "reviewed": 0, "auto": 0, "with_bibs": 0, "not_scanned": 0}
    for b in batches(root):
        reads = load_reads(b)
        sug = suggestions_for(reads, start, prefill_at)
        rev = {}
        if (b / REVIEW).exists():
            try:
                rev = json.loads((b / REVIEW).read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print(f"! could not read {b / REVIEW}; using model reads for that batch")
        for p in photos_in(b):
            if p.name not in reads:
                stats["not_scanned"] += 1
                continue
            key = key_of(root, p)
            if p.name in rev:
                numbers = rev[p.name].get("numbers", [])
                stats["reviewed"] += 1
            else:
                numbers = sug.get(p.name, {}).get("numbers", [])
                stats["auto"] += 1
            model = sorted({norm(h["text"]) for h in reads[p.name]["hits"] if h["conf"] >= 0.1 and norm(h["text"])})
            rows_csv.append([key, ", ".join(numbers)])
            review_all[key] = {"numbers": numbers, "model_numbers": model}
            stats["photos"] += 1
            stats["with_bibs"] += bool(numbers)
    out_dir = root / "_publish"
    out_dir.mkdir(exist_ok=True)
    csv_path, rev_path = out_dir / "bib_export.csv", out_dir / "review_all.json"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["image_name", "bib_numbers"])
        w.writerows(rows_csv)
    rev_path.write_text(json.dumps(review_all, ensure_ascii=False), encoding="utf-8")
    return csv_path, rev_path, stats


def run_node(script: str, *argv: str, event: str) -> None:
    web = ROOT / "web"
    env = dict(os.environ, EVENT=event)
    cmd = ["node", f"scripts/{script}", *argv]
    print("\n$ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=web, env=env, shell=(os.name == "nt"))
    if r.returncode:
        raise SystemExit(f"{script} failed (exit {r.returncode}). Fix and re-run publish; finished work is kept.")


def cmd_publish(args) -> int:
    root = Path(args.root).resolve()
    start = load_start_list(args.start_list)
    csv_path, rev_path, s = export(root, start, args.prefill_at)
    print(f"{s['photos']} photos ({s['reviewed']} reviewed, {s['auto']} automatic), "
          f"{s['with_bibs']} with at least one bib -> {csv_path}")
    if s["not_scanned"]:
        print(f"! {s['not_scanned']} photo(s) not scanned yet: run  raceday.py scan  first (they are left out)")
    if args.export_only:
        return 0
    if not args.skip_photos:
        extra = ["--photographer", args.photographer] if args.photographer else []
        run_node("publish-photos.mjs", "--dir", str(root), *extra, event=args.event)
    run_node("import-bibs.mjs", "--csv", str(csv_path), "--review", str(rev_path), event=args.event)
    if not args.no_rebuild:
        run_node("publish-event.mjs", event=args.event)
    print("\nDone. The site updates in a few minutes.")
    return 0


def cmd_status(args) -> int:
    root = Path(args.root).resolve()
    print(f"{'batch':40} {'photos':>7} {'scanned':>8} {'reviewed':>9} {'auto bibs':>10}")
    tot = [0, 0, 0, 0]
    for b in batches(root):
        ph = photos_in(b)
        reads = load_reads(b)
        rev = json.loads((b / REVIEW).read_text(encoding="utf-8")) if (b / REVIEW).exists() else {}
        sug = json.loads((b / SUGGESTIONS).read_text(encoding="utf-8")) if (b / SUGGESTIONS).exists() else {}
        row = [len(ph), sum(p.name in reads for p in ph), sum(p.name in rev for p in ph),
               sum(1 for p in ph if sug.get(p.name, {}).get("numbers"))]
        tot = [a + c for a, c in zip(tot, row)]
        name = str(b.relative_to(root)) or "."
        print(f"{name[:40]:40} {row[0]:>7} {row[1]:>8} {row[2]:>9} {row[3]:>10}")
    print(f"{'TOTAL':40} {tot[0]:>7} {tot[1]:>8} {tot[2]:>9} {tot[3]:>10}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "publish", "status"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", required=True, help="folder that holds the batch folders")
        sp.add_argument("--start-list", help="txt (one bib per line) or csv with a 'bib' column")
        sp.add_argument("--prefill-at", type=float, default=0.5, help="auto-accept reads at or above this confidence")
        if name == "scan":
            sp.add_argument("--imgsz", type=int, default=1280)
            sp.add_argument("--det-conf", type=float, default=0.25)
            sp.add_argument("--expand", type=float, default=0.15, help="crop margin around each box")
            sp.add_argument("--cpu", action="store_true")
        if name == "publish":
            sp.add_argument("--event", default="zagreb-2026")
            sp.add_argument("--photographer")
            sp.add_argument("--export-only", action="store_true", help="only write _publish/bib_export.csv")
            sp.add_argument("--skip-photos", action="store_true", help="tags only, photos already uploaded")
            sp.add_argument("--no-rebuild", action="store_true", help="do not trigger the site rebuild")
    args = ap.parse_args()
    return {"scan": cmd_scan, "publish": cmd_publish, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
