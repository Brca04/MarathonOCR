#!/usr/bin/env python3
"""Race day: photos in, searchable site out, batch by batch.

Layout: one root folder, one sub-folder per batch as it arrives, e.g.

    D:\\ZG26\\
        01_start_ana\\        *.jpg
        02_10k_marko\\        *.jpg
        03_finish_ana\\       *.jpg

Any folder under the root that directly holds photos is a batch. A batch can
arrive while another is being processed; just run the command again.

    python scripts/raceday.py scan    --root D:\\ZG26      # duplicates aside + recognise new photos (GPU)
    python scripts/raceday.py check   --root D:\\ZG26      # Claude Haiku second look (about $1 per 3,000 photos)
    python scripts/raceday.py recheck --root D:\\ZG26      # close-ups of what is still in doubt (local AI + Haiku)
    (optional) review in the desktop app:  python review_desktop.py D:\\ZG26
    python scripts/raceday.py publish --root D:\\ZG26      # upload + tag + rebuild the site
    python scripts/raceday.py status  --root D:\\ZG26      # what is where

Tidy up (one flat folder per photographer, photos ZgMaraton26_ImePrezime_1.jpg ...):
    python scripts/raceday.py organize --root D:\\ZG26          # shows the plan
    python scripts/raceday.py organize --root D:\\ZG26 --go     # does it; scan results and reviews move along

Second reviewer on another PC:
    python scripts/raceday.py pack  --root D:\\ZG26 --batch 01_start   # zip to send (photos that need a person)
    python scripts/raceday.py merge --root D:\\ZG26 --file review_01_start.json   # their file back in

`scan` runs the old detector (best.pt) and the fine-tuned one (best_v3.pt)
together, merges their boxes, reads every box with EasyOCR, and writes in each
batch folder:
    .raceday_reads.jsonl            every read, one photo per line (resume point)
    .marathon_ocr_suggestions.json  what the review app pre-fills and sorts by

`publish` collects every batch: numbers you confirmed in the review app win;
photos nobody reviewed take the confident reads (on the start list, if given).
Then it runs the web scripts: publish-photos (resize + upload to R2),
import-bibs (tags), publish-event (export + rebuild via the deploy hook).

`scan` first moves exact duplicate photos (same file content, other name) into
a hidden `.duplicates` folder in their batch, so nobody reviews or uploads a
photo twice. Without a start list only 3-4 digit reads count as bibs.

`check` sends every scanned photo once to Claude Haiku (ANTHROPIC_API_KEY in
.env) and combines both readings: a bib both read, or one Haiku reads clearly,
is accepted; only real doubt is left for the review app.

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
HAIKU = ".raceday_haiku.jsonl"
RECHECK = ".raceday_recheck.jsonl"
DUPES = ".duplicates"
# Claude Haiku 5.5, USD per million tokens (input, output), for the estimate only.
PRICE = (0.10, 0.50)
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


def load_haiku(batch: Path) -> dict[str, dict]:
    p = batch / HAIKU
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["file"]] = r
    return out


def load_recheck(batch: Path) -> dict[str, dict]:
    p = batch / RECHECK
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["file"]] = r
    return out


def box_key(b) -> str:
    return ",".join(str(round(v)) for v in b[:4])


def plausible(t: str, start: set[str] | None) -> bool:
    """A read that can be a bib: on the start list, or 3-4 digits without one."""
    return (t in start) if start is not None else 3 <= len(t) <= 4


def dedupe(root: Path) -> int:
    """Move exact duplicate photos (same bytes, other name) into <batch>/.duplicates.

    The first name in sort order stays. Hashes are cached per batch, keyed by
    name + size + mtime, so later runs only hash new photos.
    """
    import hashlib

    seen: dict[str, Path] = {}
    moved = 0
    for b in batches(root):
        cache_p = b / ".raceday_hashes.json"
        cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
        fresh = {}
        for p in photos_in(b):
            st_ = p.stat()
            sig = f"{st_.st_size}:{int(st_.st_mtime)}"
            c = cache.get(p.name)
            if c and c[0] == sig:
                h = c[1]
            else:
                hh = hashlib.sha1()
                with p.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        hh.update(chunk)
                h = hh.hexdigest()
            if h in seen:
                dest_dir = b / DUPES
                dest_dir.mkdir(exist_ok=True)
                dest = dest_dir / p.name
                if not dest.exists():
                    p.rename(dest)
                    moved += 1
                    continue
            seen.setdefault(h, p)
            fresh[p.name] = [sig, h]
        cache_p.write_text(json.dumps(fresh), encoding="utf-8")
    return moved


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

    def __init__(self, weights: list[Path], conf: float, imgsz: int, tiles: bool = True):
        from marathon_ocr.detectors import YOLOBibDetector

        self.parts = [YOLOBibDetector(str(w), conf=conf, imgsz=imgsz) for w in weights]
        # Also search 4 overlapping quarters: each is shrunk far less than the
        # whole photo, so small background bibs become findable.
        self.tiles = tiles

    def warmup(self) -> None:
        for p in self.parts:
            p.warmup()

    def detect(self, image):
        from dataclasses import replace

        boxes = [b for p in self.parts for b in p.detect(image)]
        if self.tiles:
            W, H = image.size
            tw, th = int(W * 0.58), int(H * 0.58)
            for tx, ty in ((0, 0), (W - tw, 0), (0, H - th), (W - tw, H - th)):
                tile = image.crop((tx, ty, tx + tw, ty + th))
                for p in self.parts:
                    for b in p.detect(tile):
                        boxes.append(replace(b, x0=b.x0 + tx, x1=b.x1 + tx, y0=b.y0 + ty, y1=b.y1 + ty))
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


def suggestions_for(rows: dict[str, dict], start: set[str] | None, prefill_at: float,
                    haiku: dict[str, dict] | None = None, present: set[str] | None = None,
                    recheck: dict[str, dict] | None = None) -> dict:
    """Review-app format, keyed by bare file name.

    Without Haiku: confident plausible model reads are accepted, the rest is for you.
    With Haiku: a bib both read, or one Haiku reads clearly, is accepted; a model
    read Haiku does not see, or a bib Haiku reads only partly, is left for you.
    """
    haiku = haiku or {}
    recheck = recheck or {}
    out = {}
    for name, r in rows.items():
        if present is not None and name not in present:
            continue  # set aside as a duplicate, or gone
        best: dict[str, dict] = {}
        for h in r["hits"]:
            t = norm(h["text"])
            if t and (t not in best or h["conf"] > best[t]["conf"]):
                best[t] = h
        hk = haiku.get(name)
        h_ok = bool(hk) and not hk.get("error")
        h_nums = [n for n in (hk or {}).get("numbers", []) if plausible(n, start)] if h_ok else []
        h_clear = {n for n in h_nums if (hk or {}).get("clarity", {}).get(n) == "clear"}
        rc = recheck.get(name) or {}
        rc_crops = {c["key"]: c for c in rc.get("crops", [])}
        tiles = rc.get("tiles") or {}
        tile_clear = {n for n in tiles.get("numbers", [])
                      if tiles.get("clarity", {}).get(n) == "clear" and plausible(n, start)}
        swapped: dict[str, str] = {}

        persons, numbers, unsure = [], [], 0
        for t, h in sorted(best.items(), key=lambda kv: -kv[1]["conf"]):
            if h["conf"] < 0.1:
                continue
            real = plausible(t, start)
            if h_ok:
                take = real and (t in h_nums or h["conf"] >= max(prefill_at, 0.9))
                # Haiku did not see it: a weak model read (often texture or a
                # half-hidden bib) is dropped quietly; a strong one is a real
                # disagreement and goes to you.
                doubt = real and not take and h["conf"] >= 0.6
                verdict = "agree" if (real and t in h_nums) else ("confident" if take else "model_only")
            else:
                take = real and h["conf"] >= prefill_at
                doubt = real and not take and h["conf"] >= 0.3
                verdict = "confident" if take else "model_only"
            extra = []
            c = rc_crops.get(box_key(h["bbox"])) if doubt else None
            if c is not None:
                # Close-up of this bib at full resolution: Haiku + the local AI again.
                ch = c.get("haiku") or {}
                c_clear = [n for n in ch.get("numbers", []) if ch.get("clarity", {}).get(n) == "clear"
                           and plausible(n, start)]
                c_part = [n for n in ch.get("numbers", []) if n not in c_clear and plausible(n, start)]
                local = c.get("local") or []
                l_best, l_conf = (local[0][0], local[0][1]) if local else ("", 0.0)
                if t in c_clear or (t in c_part and l_best == t and l_conf >= 0.8):
                    take, doubt, verdict = True, False, "agree"
                elif len(c_clear) == 1 and l_best == c_clear[0] and l_conf >= 0.5:
                    # Both close-up readers agree on another number: the first read was wrong.
                    swapped[t] = c_clear[0]
                    take, doubt, verdict = False, False, "replaced"
                    if c_clear[0] not in numbers:
                        numbers.append(c_clear[0])
                else:
                    extra = [n for n in c_clear + c_part if n != t]
            if take and t not in numbers:
                numbers.append(t)
            unsure += doubt
            persons.append(dict(box=h["bbox"], ocr=[[t, h["conf"]]], unsure=not take, verdict=verdict,
                                needs_human=doubt, on_start_list=real,
                                haiku=dict(numbers=([t] if t in h_nums else []) + extra) if (t in h_nums or extra) else None))
        # Bibs only Haiku read (often the small ones in a crowd). A clear one is
        # accepted; a partial one is only Haiku's guess at a blurred background
        # bib, so it is offered in the review app but does not flag the photo.
        for n in h_nums + sorted(tile_clear - set(h_nums)):
            if n in best or n in swapped.values():
                continue
            clear = n in h_clear or n in tile_clear  # tiles: a full-resolution quarter of the photo
            if clear and n not in numbers:
                numbers.append(n)
            persons.append(dict(box=[0, 0, r.get("w", 0), r.get("h", 0)], ocr=[], unsure=not clear,
                                verdict="whole_only", needs_human=False, on_start_list=True,
                                haiku=dict(numbers=[n], clarity={n: "clear" if clear else "partial"})))
        out[Path(name).name] = dict(numbers=numbers, needs_human=unsure, persons=persons,
                                    source=("raceday+haiku+recheck" if rc else "raceday+haiku") if h_ok else "raceday",
                                    w=r.get("w"), h=r.get("h"))
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

    moved = dedupe(root)
    if moved:
        print(f"{moved} duplicate photo(s) set aside in .duplicates (same file, other name)")

    todo: list[tuple[Path, Path]] = []
    per_batch: dict[Path, dict] = {}
    for b in batches(root):
        if args.rescan:
            # Read everything again (e.g. with the quarter search). Haiku's whole-photo
            # look and people's reviews are kept; old close-ups refer to old boxes.
            for f in (READS, RECHECK):
                if (b / f).exists():
                    (b / f).replace(b / (f + ".old"))
        done = load_reads(b)
        per_batch[b] = done
        todo += [(b, p) for p in photos_in(b) if p.name not in done]
    total = sum(len(photos_in(b)) for b in per_batch)
    print(f"{len(per_batch)} batch(es), {total} photos, {len(todo)} new")

    if todo:
        detector = CombinedDetector(weights, conf=args.det_conf, imgsz=args.imgsz, tiles=not args.no_tiles)
        pipe = BibPipeline(detector, build("easyocr", gpu=not args.cpu), min_height=64,
                           expand=args.expand, min_confidence=0.0)
        pipe.warmup()
        print(f"models: {', '.join(w.name for w in weights)}  (imgsz {args.imgsz}, det-conf {args.det_conf}, "
              f"{'whole photo + 4 quarters' if not args.no_tiles else 'whole photo only'})")

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

    write_suggestions(root, start, args.prefill_at)
    print("Next:  raceday.py check  (Haiku second look), then review, then  raceday.py publish")
    return 0


def write_suggestions(root: Path, start: set[str] | None, prefill_at: float) -> None:
    need = auto = 0
    for b in batches(root):
        present = {p.name for p in photos_in(b)}
        sug = suggestions_for(load_reads(b), start, prefill_at, load_haiku(b), present, load_recheck(b))
        (b / SUGGESTIONS).write_text(json.dumps(sug, ensure_ascii=False, indent=1), encoding="utf-8")
        need += sum(1 for v in sug.values() if v["needs_human"])
        auto += sum(1 for v in sug.values() if v["numbers"])
    print(f"review app updated: {auto} photo(s) with bibs, {need} still need you")


# --------------------------------------------------------------------------- Haiku second look

def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cmd_check(args) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from PIL import Image, ImageOps

    from marathon_ocr.verify import HaikuVerifier

    load_env()
    root = Path(args.root).resolve()
    start = load_start_list(args.start_list)
    jobs = []
    for b in batches(root):
        reads, done = load_reads(b), load_haiku(b)
        retry = {n for n, r in done.items() if r.get("error")}
        jobs += [(b, p) for p in photos_in(b) if p.name in reads and (p.name not in done or p.name in retry)]
    if args.limit:
        jobs = jobs[: args.limit]
    est = len(jobs) * (2300 * PRICE[0] + 150 * PRICE[1]) / 1e6
    print(f"{len(jobs)} photo(s) for Haiku ({args.model}), estimated ${est:.2f}")
    if not jobs or args.dry_run:
        return 0

    v = HaikuVerifier(model=args.model)
    v.warmup()

    def one(b: Path, p: Path):
        reads = load_reads_cache[b][p.name]
        hint = sorted({norm(h["text"]) for h in reads["hits"] if h["conf"] >= 0.3 and plausible(norm(h["text"]), start)})
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            # Same frame as the scan, so nothing needs rescaling later.
            if reads.get("w") and im.width != reads["w"]:
                im = im.resize((reads["w"], reads["h"]))
            r = v.read_whole(im, hint)
        return b, p, r

    load_reads_cache = {b: load_reads(b) for b in {b for b, _ in jobs}}
    handles, spent_in, spent_out, n, failed = {}, 0, 0, 0, 0
    t0 = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(one, b, p) for b, p in jobs]
            for f in as_completed(futs):
                b, p, r = f.result()
                fh = handles.get(b) or handles.setdefault(b, (b / HAIKU).open("a", encoding="utf-8"))
                fh.write(json.dumps(dict(file=p.name, numbers=r.numbers, clarity=r.clarity, note=r.note,
                                         error=r.error, model=args.model), ensure_ascii=False) + "\n")
                fh.flush()
                spent_in += r.input_tokens
                spent_out += r.output_tokens
                failed += bool(r.error)
                n += 1
                if n % 50 == 0 or n == len(jobs):
                    cost = (spent_in * PRICE[0] + spent_out * PRICE[1]) / 1e6
                    print(f"  {n}/{len(jobs)}  ${cost:.2f}  {time.perf_counter() - t0:.0f}s"
                          + (f"  ({failed} failed, re-run to retry)" if failed else ""), flush=True)
    finally:
        for fh in handles.values():
            fh.close()
    write_suggestions(root, start, args.prefill_at)
    return 0


# --------------------------------------------------------------------------- export + publish

def export(root: Path, start: set[str] | None, prefill_at: float) -> tuple[Path, Path, dict]:
    rows_csv, review_all = [], {}
    stats = {"photos": 0, "reviewed": 0, "auto": 0, "with_bibs": 0, "not_scanned": 0}
    for b in batches(root):
        reads = load_reads(b)
        sug = suggestions_for(reads, start, prefill_at, load_haiku(b), None, load_recheck(b))
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
    print(f"{'batch':40} {'photos':>7} {'scanned':>8} {'reviewed':>9} {'auto bibs':>10} {'need you':>9}")
    tot = [0, 0, 0, 0, 0]
    for b in batches(root):
        ph = photos_in(b)
        reads = load_reads(b)
        rev = json.loads((b / REVIEW).read_text(encoding="utf-8")) if (b / REVIEW).exists() else {}
        sug = json.loads((b / SUGGESTIONS).read_text(encoding="utf-8")) if (b / SUGGESTIONS).exists() else {}
        row = [len(ph), sum(p.name in reads for p in ph), sum(p.name in rev for p in ph),
               sum(1 for p in ph if sug.get(p.name, {}).get("numbers")),
               sum(1 for p in ph if sug.get(p.name, {}).get("needs_human") and p.name not in rev)]
        tot = [a + c for a, c in zip(tot, row)]
        name = str(b.relative_to(root)) or "."
        print(f"{name[:40]:40} {row[0]:>7} {row[1]:>8} {row[2]:>9} {row[3]:>10} {row[4]:>9}")
    print(f"{'TOTAL':40} {tot[0]:>7} {tot[1]:>8} {tot[2]:>9} {tot[3]:>10} {tot[4]:>9}")
    return 0


# --------------------------------------------------------------------------- close-ups of what is in doubt

RECHECK_PRICE_PER_PHOTO = 0.0015  # rough: a few small crops, sometimes 4 tiles


def _doubts(b: Path, start, prefill_at) -> dict[str, dict]:
    """Per photo: the boxes still in doubt after Haiku, and whether Haiku-only
    partial reads (no box) need the four-tile look."""
    sug = suggestions_for(load_reads(b), start, prefill_at, load_haiku(b), {p.name for p in photos_in(b)})
    out = {}
    for name, e in sug.items():
        boxes = [p["box"] for p in e["persons"] if p.get("needs_human") and p.get("verdict") != "whole_only"]
        partial = any(p.get("verdict") == "whole_only" and p.get("unsure") for p in e["persons"])
        if boxes or partial:
            out[name] = {"boxes": boxes, "tiles": partial, "numbers": e["numbers"]}
    return out


def cmd_recheck(args) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from PIL import Image, ImageOps

    from marathon_ocr.recognizers import build
    from marathon_ocr.verify import HaikuVerifier, WHOLE_PROMPT

    load_env()
    root = Path(args.root).resolve()
    start = load_start_list(args.start_list)
    jobs, before = [], {}
    for b in batches(root):
        done = load_recheck(b)
        rev = json.loads((b / REVIEW).read_text(encoding="utf-8")) if (b / REVIEW).exists() else {}
        for name, d in _doubts(b, start, args.prefill_at).items():
            if name in done and not (done[name].get("error")):
                continue
            # --eval: only photos a person already reviewed (their answer is the truth);
            # normal run: only photos nobody has reviewed yet.
            if args.eval != (name in rev):
                continue
            jobs.append((b, name, d))
            before[(b, name)] = d["numbers"]
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"{len(jobs)} photo(s) with doubts for close-ups ({args.model}), "
          f"estimated ${len(jobs) * RECHECK_PRICE_PER_PHOTO:.2f}")
    if not jobs or args.dry_run:
        return 0

    v = HaikuVerifier(model=args.model)
    v.warmup()
    ocr = build("easyocr", gpu=not args.cpu)
    ocr.warmup()
    ocr_lock = threading.Lock()  # one GPU reader, several photo threads

    def one(b: Path, name: str, d: dict):
        with Image.open(b / name) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
        W, H = im.size
        crops = []
        for box in d["boxes"]:
            x0, y0, x1, y1 = box
            w, h = x1 - x0, y1 - y0
            # Haiku: the bib plus some of the runner, at the photo's own resolution.
            mx, my = max(w * 0.6, 60), max(h * 0.8, 60)
            hc = im.crop((max(0, x0 - mx), max(0, y0 - my), min(W, x1 + mx), min(H, y1 + my)))
            hr = v.read(hc, None)
            # Local AI: tight crop, enlarged so the digits are ~3x taller than before.
            lc = im.crop((max(0, x0 - w * 0.08), max(0, y0 - h * 0.08), min(W, x1 + w * 0.08), min(H, y1 + h * 0.08)))
            target_h = int(min(400, max(160, lc.height * 3)))
            lc = lc.resize((max(1, round(lc.width * target_h / max(lc.height, 1))), target_h), Image.LANCZOS)
            with ocr_lock:
                local = ocr.read(lc).candidates[:3]
            crops.append(dict(key=box_key(box), local=[[t, round(c, 4)] for t, c in local],
                              haiku=dict(numbers=hr.numbers, clarity=hr.clarity, error=hr.error),
                              tokens=[hr.input_tokens, hr.output_tokens]))
        tiles = None
        if d["tiles"]:
            nums, clar, err, tin, tout = [], {}, None, 0, 0
            tw, th = int(W * 0.58), int(H * 0.58)  # 4 overlapping quarters
            for tx, ty in ((0, 0), (W - tw, 0), (0, H - th), (W - tw, H - th)):
                tr = v.read(im.crop((tx, ty, tx + tw, ty + th)), d["numbers"], prompt=WHOLE_PROMPT,
                            max_side=1568, max_tokens=1200)
                err = err or tr.error
                tin, tout = tin + tr.input_tokens, tout + tr.output_tokens
                for n in tr.numbers:
                    if n not in nums:
                        nums.append(n)
                    if tr.clarity.get(n) == "clear":
                        clar[n] = "clear"
                    else:
                        clar.setdefault(n, "partial")
            tiles = dict(numbers=nums, clarity=clar, error=err, tokens=[tin, tout])
        return b, name, dict(file=name, crops=crops, tiles=tiles, model=args.model,
                             error=next((c["haiku"]["error"] for c in crops if c["haiku"]["error"]), None)
                             or (tiles or {}).get("error"))

    handles, spent_in, spent_out, n = {}, 0, 0, 0
    t0 = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for f in as_completed([pool.submit(one, b, name, d) for b, name, d in jobs]):
                b, name, row = f.result()
                fh = handles.get(b) or handles.setdefault(b, (b / RECHECK).open("a", encoding="utf-8"))
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                for c in row["crops"]:
                    spent_in += c["tokens"][0]; spent_out += c["tokens"][1]
                if row["tiles"]:
                    spent_in += row["tiles"]["tokens"][0]; spent_out += row["tiles"]["tokens"][1]
                n += 1
                if n % 25 == 0 or n == len(jobs):
                    cost = (spent_in * PRICE[0] + spent_out * PRICE[1]) / 1e6
                    print(f"  {n}/{len(jobs)}  ${cost:.2f}  {time.perf_counter() - t0:.0f}s", flush=True)
    finally:
        for fh in handles.values():
            fh.close()

    if args.eval:
        evaluate(root, start, args.prefill_at)
    write_suggestions(root, start, args.prefill_at)
    return 0


def evaluate(root: Path, start, prefill_at) -> None:
    """Compare the pipeline with and without close-ups against what people
    confirmed in the review app, on the photos that were in doubt."""
    tot = {"photos": 0, "b_ok": 0, "a_ok": 0, "b_flag": 0, "a_flag": 0,
           "b_tp": 0, "b_fp": 0, "a_tp": 0, "a_fp": 0, "truth": 0}
    for b in batches(root):
        rc = load_recheck(b)
        if not (b / REVIEW).exists() or not rc:
            continue
        rev = json.loads((b / REVIEW).read_text(encoding="utf-8"))
        present = {p.name for p in photos_in(b)}
        reads, hk = load_reads(b), load_haiku(b)
        bef = suggestions_for(reads, start, prefill_at, hk, present)
        aft = suggestions_for(reads, start, prefill_at, hk, present, rc)
        for name in rc:
            if name not in rev or name not in bef:
                continue
            truth = set(rev[name].get("numbers", []))
            B, A = set(bef[name]["numbers"]), set(aft[name]["numbers"])
            tot["photos"] += 1
            tot["truth"] += len(truth)
            tot["b_ok"] += B == truth
            tot["a_ok"] += A == truth
            tot["b_flag"] += bool(bef[name]["needs_human"])
            tot["a_flag"] += bool(aft[name]["needs_human"])
            tot["b_tp"] += len(B & truth); tot["b_fp"] += len(B - truth)
            tot["a_tp"] += len(A & truth); tot["a_fp"] += len(A - truth)
    t = tot
    if not t["photos"]:
        print("evaluation: no reviewed photos with close-ups yet")
        return
    print(f"\nEvaluation on {t['photos']} reviewed photo(s) that were in doubt "
          f"({t['truth']} bibs confirmed by people):")
    print(f"  {'':28}{'before':>10}{'with close-ups':>16}")
    print(f"  {'photos exactly right':28}{t['b_ok']:>10}{t['a_ok']:>16}")
    print(f"  {'bibs found (of confirmed)':28}{t['b_tp']:>10}{t['a_tp']:>16}")
    print(f"  {'wrong bibs added':28}{t['b_fp']:>10}{t['a_fp']:>16}")
    print(f"  {'still flagged for a person':28}{t['b_flag']:>10}{t['a_flag']:>16}")


# --------------------------------------------------------------------------- second reviewer

PACK_README = """MarathonOCR review pack: {batch}  ({n} photos)

1. Unzip this folder anywhere (right-click -> Extract All). Do not run it from inside the zip.
2. Double-click  start_review.bat . The review window opens (no browser, no internet).
   (If this pack has no "python" folder, install Python 3.12 from python.org first.)
3. Type your name at the top. For each photo keep the right numbers, remove
   wrong ones, type missed ones (just start typing digits, Enter adds),
   then E (confirm & next). Q goes back. Everything saves by itself.
4. When done: "Save file to send back" (bottom right) and send that .json back.
"""

START_BAT = """@echo off
rem No if-blocks: a folder name like "review (1)" would break them.
cd /d "%~dp0"
if not exist "python\\python.exe" goto system
rem Self-contained pack: its own Python, nothing to install.
"python\\python.exe" review_desktop.py "%~dp0{batch}"
goto end
:system
python -m pip install --quiet --disable-pip-version-check PySide6-Essentials
python review_desktop.py "%~dp0{batch}"
:end
pause
"""

KIT = "_review_kit"  # under the repo: a portable Python with the review window (Qt), made by  raceday.py kit
PY_EMBED = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"


def cmd_kit(args) -> int:
    """Build a portable Windows Python with the review app's two packages, once.
    pack then puts it into every zip, so the reviewer installs nothing."""
    import shutil
    import urllib.request
    import zipfile

    kit = ROOT / KIT / "python"
    if kit.exists():
        shutil.rmtree(kit)
    kit.mkdir(parents=True)
    zpath = ROOT / KIT / "python-embed.zip"
    print(f"downloading {PY_EMBED}")
    urllib.request.urlretrieve(PY_EMBED, zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(kit)
    # The embeddable Python ignores site-packages until its ._pth file allows it.
    pth = next(kit.glob("python3*._pth"))
    lines = [ln for ln in pth.read_text().splitlines() if ln.strip() and not ln.startswith("#import")]
    pth.write_text("\n".join(lines + ["Lib\\site-packages", "import site"]) + "\n")
    site = kit / "Lib" / "site-packages"
    site.mkdir(parents=True)
    print("installing PySide6 (the review window) into the kit (Windows 64-bit, Python 3.12)")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "--target", str(site), "--platform", "win_amd64", "--python-version", "3.12",
                        "--only-binary=:all:", "PySide6-Essentials==6.9.1"])
    if r.returncode:
        raise SystemExit("pip failed; check the internet connection and run  raceday.py kit  again")
    size = sum(f.stat().st_size for f in kit.rglob("*") if f.is_file())
    print(f"kit ready: {kit}  ({size / 1e6:.0f} MB). Every  raceday.py pack  now includes it.")
    return 0


def cmd_pack(args) -> int:
    """One zip per photographer (or per batch with --batch): the photos that
    still need a person, smaller copies, the scan results, the review app and
    (after  raceday.py kit ) its own Python."""
    import zipfile
    from concurrent.futures import ThreadPoolExecutor
    from io import BytesIO

    from PIL import Image, ImageOps

    root = Path(args.root).resolve()
    all_b = {str(b.relative_to(root)) or ".": b for b in batches(root)}
    if args.batch is not None:
        if args.batch not in all_b:
            raise SystemExit(f"no batch {args.batch!r}; batches: {', '.join(all_b)}")
        chosen = {args.batch: all_b[args.batch]}
        name = (Path(args.batch).name or root.name).replace(" ", "_")
    else:
        chosen = all_b  # every part of this folder in one zip
        name = root.name.replace(" ", "_")
    top = f"review_{name}"
    out = Path(args.out) if args.out else root / "_packs" / f"{top}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)

    plan = []  # (folder inside the zip, batch, photos, suggestions, reviews)
    for rel, b in chosen.items():
        sug = json.loads((b / SUGGESTIONS).read_text(encoding="utf-8")) if (b / SUGGESTIONS).exists() else {}
        rev = json.loads((b / REVIEW).read_text(encoding="utf-8")) if (b / REVIEW).exists() else {}
        if not sug:
            print(f"! {rel}: not scanned yet, left out")
            continue
        photos = [ph for ph in photos_in(b)
                  if args.all or (sug.get(ph.name, {}).get("needs_human") and ph.name not in rev)]
        if not photos:
            continue
        inner = f"{top}/{name}" if rel == "." else f"{top}/{name}/{Path(rel).as_posix()}"
        if args.batch is not None:
            inner = f"{top}/{name}"
        keep = {ph.name for ph in photos}
        plan.append((inner, b, photos,
                     {k: v for k, v in sug.items() if k in keep}, {k: v for k, v in rev.items() if k in keep}))
    total = sum(len(x[2]) for x in plan)
    if not total:
        raise SystemExit("nothing to pack: no photo here still needs a person (use --all for every photo)")
    print(f"packing {total} photo(s) from {len(plan)} part(s) at {args.size}px -> {out}")

    def small(ph: Path) -> tuple[str, bytes]:
        with Image.open(ph) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((args.size, args.size), Image.LANCZOS)
            buf = BytesIO()
            im.save(buf, "JPEG", quality=85)
        return ph.name, buf.getvalue()

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        z.write(ROOT / "review_desktop.py", f"{top}/review_desktop.py")
        z.writestr(f"{top}/start_review.bat", START_BAT.format(batch=name).replace("\n", "\r\n"))
        z.writestr(f"{top}/README.txt", PACK_README.format(batch=name, n=total))
        kit = ROOT / KIT / "python"
        if kit.exists() and not args.no_kit:
            files = [f for f in kit.rglob("*") if f.is_file()]
            print(f"adding the portable Python ({len(files)} files)")
            for f in files:
                z.write(f, f"{top}/python/{f.relative_to(kit).as_posix()}", compress_type=zipfile.ZIP_DEFLATED)
        elif not args.no_kit:
            print("! no portable Python yet (run  raceday.py kit  once); the reviewer will need Python installed")
        done = 0
        with ThreadPoolExecutor(max_workers=6) as pool:
            for inner, b, photos, sug, rev in plan:
                z.writestr(f"{inner}/{SUGGESTIONS}", json.dumps(sug, ensure_ascii=False))
                z.writestr(f"{inner}/{REVIEW}", json.dumps(rev, ensure_ascii=False))
                for fname, data in pool.map(small, photos):
                    z.writestr(f"{inner}/{fname}", data)
                    done += 1
                    if done % 100 == 0 or done == total:
                        print(f"  {done}/{total}", flush=True)
    print(f"done: {out}  ({out.stat().st_size / 1e6:.0f} MB). Send it; they unzip and open start_review.bat.")
    return 0


def cmd_merge(args) -> int:
    """Take a reviewer's file back. A file from a pack with several parts holds
    each part separately ({"parts": {part: reviews}}); a single-folder file is
    matched to the batch whose photos it names."""
    root = Path(args.root).resolve()
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    all_b = {str(b.relative_to(root)) or ".": b for b in batches(root)}
    if isinstance(data, dict) and isinstance(data.get("parts"), dict):
        jobs = []
        for rel, theirs in data["parts"].items():
            by_posix = {Path(k).as_posix(): v for k, v in all_b.items()}
            b = by_posix.get(Path(rel.replace("\\", "/")).as_posix())
            if b is None:
                print(f"! part {rel!r} not found under {root}, skipped")
                continue
            jobs.append((b, theirs))
    else:
        if args.batch:
            if args.batch not in all_b:
                raise SystemExit(f"no batch {args.batch!r}; batches: {', '.join(all_b)}")
            b = all_b[args.batch]
        else:
            b = max(all_b.values(), key=lambda bb: len({ph.name for ph in photos_in(bb)} & set(data)))
        jobs = [(b, data)]
    for b, theirs in jobs:
        known = {ph.name for ph in photos_in(b)}
        mine = json.loads((b / REVIEW).read_text(encoding="utf-8")) if (b / REVIEW).exists() else {}
        took = kept = unknown = 0
        for name, e in theirs.items():
            if name not in known:
                unknown += 1
                continue
            m = mine.get(name)
            # Newer review wins (entries carry a save time); a photo only they did is simply added.
            if m is None or e.get("at", 0) > m.get("at", 0):
                mine[name] = e
                took += 1
            else:
                kept += 1
        tmp = (b / REVIEW).with_suffix(".tmp")
        tmp.write_text(json.dumps(mine, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(b / REVIEW)
        print(f"{b.relative_to(root) or '.'}: {took} photo(s) taken, {kept} kept (yours were newer)"
              + (f", {unknown} unknown name(s) skipped" if unknown else ""))
    return 0


# --------------------------------------------------------------------------- organize

def _natural(s: str):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _slug(name: str) -> str:
    import unicodedata
    a = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(ch for ch in a.title() if ch.isalnum())


def _shot_time(p: Path) -> str | None:
    """When the photo was taken (EXIF), as 'YYYY:MM:DD HH:MM:SS.sss', or None."""
    try:
        from PIL import Image
        with Image.open(p) as im:
            ex = im.getexif()
            sub = ex.get_ifd(0x8769)
            t = sub.get(36867) or ex.get(306)
            if not t:
                return None
            ms = str(sub.get(37521) or "0").strip()[:3]
            return f"{str(t).strip()}.{ms.zfill(3)}"
    except Exception:
        return None


def _shot_order(photos: list[Path], by_name: bool = False) -> list[Path]:
    """New photos in the order they were taken, so shots of the same runners stay
    together even when two cameras are mixed (DSC_, _GRI, RSM_ ...). Falls back to
    the file name when any photo has no capture time."""
    named = sorted(photos, key=lambda q: _natural(q.name))
    if by_name or not photos:
        return named
    times = {p: _shot_time(p) for p in named}
    if any(t is None for t in times.values()):
        return named
    return sorted(named, key=lambda q: times[q])


def cmd_organize(args) -> int:
    """One flat folder per photographer, photos named <prefix>_<ImePrezime>_<n>.
    Scan results, Haiku checks and reviews move with their photos, so nothing
    has to be scanned or reviewed again. Without --go it only shows the plan."""
    import re

    root = Path(args.root).resolve()
    photographers = [d for d in sorted(root.iterdir(), key=lambda d: _natural(d.name))
                     if d.is_dir() and not d.name.startswith((".", "_"))]
    jsonl_kinds = [READS, HAIKU, RECHECK, READS + ".old", RECHECK + ".old", HAIKU + ".old"]
    json_kinds = [SUGGESTIONS, REVIEW, ".raceday_hashes.json"]
    total = 0
    for ph in photographers:
        slug = _slug(ph.name)
        pat = re.compile(rf"^{re.escape(args.prefix)}_{re.escape(slug)}_(\d+)$", re.I)
        bs = sorted(batches(ph), key=lambda b: (b != ph, _natural(str(b.relative_to(ph)))))
        kept, todo = [], []
        for b in bs:
            for p in _shot_order(photos_in(b), by_name=args.by_name):
                m = pat.match(p.stem) if b == ph else None
                (kept if m else todo).append((b, p))
        n = max((int(pat.match(p.stem).group(1)) for _, p in kept), default=0)
        plan = []
        for b, p in todo:
            n += 1
            plan.append((b, p, f"{args.prefix}_{slug}_{n}{p.suffix.lower()}"))
        total += len(plan)
        print(f"{ph.name}: {len(kept) + len(plan)} photo(s) in {len(bs)} folder(s) -> one folder; "
              f"{len(plan)} to rename" + (f", {len(kept)} already named" if kept else ""))
        for b, p, new in plan[:2] + plan[-1:] if len(plan) > 3 else plan:
            print(f"    {p.relative_to(ph)}  ->  {new}")
        if not args.go or not plan:
            continue

        # 1. a log first: old path -> new name, so any step can be traced back
        with (ph / "_rename_log.csv").open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            for b, p, new in plan:
                w.writerow([p.relative_to(ph).as_posix(), new])
        rename = {b: {} for b in bs}
        for b, p, new in plan:
            rename[b][p.name] = new

        # 2. the results files of every folder, re-keyed to the new names, into the photographer folder
        lines = {k: [] for k in jsonl_kinds}
        dicts = {k: {} for k in json_kinds}
        for b in bs:
            mp = rename[b]
            for k in jsonl_kinds:
                f = b / k
                if f.exists():
                    for ln in f.read_text(encoding="utf-8").splitlines():
                        if ln.strip():
                            r = json.loads(ln)
                            r["file"] = mp.get(r.get("file"), r.get("file"))
                            lines[k].append(json.dumps(r, ensure_ascii=False))
            for k in json_kinds:
                f = b / k
                if f.exists():
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        d = {}
                    for name, v in d.items():
                        dicts[k][mp.get(name, name)] = v

        # 3. the photos
        moved = 0
        for b, p, new in plan:
            dest = ph / new
            if dest.exists():
                print(f"  ! {new} already exists, left {p.relative_to(ph)} where it is")
                continue
            p.rename(dest)
            moved += 1

        # 4. old results files and set-aside duplicates out of the way, then the merged ones in
        for b in bs:
            if b == ph:
                continue
            tag = "_".join(b.relative_to(ph).parts).replace(" ", "_")
            for f in list(b.iterdir()):
                if f.name.startswith(".raceday_") or f.name.startswith(".marathon_ocr_"):
                    (ph / "_old_data" / tag).mkdir(parents=True, exist_ok=True)
                    f.replace(ph / "_old_data" / tag / f.name)
                elif f.name == DUPES and f.is_dir():
                    dd = ph / DUPES / tag
                    dd.mkdir(parents=True, exist_ok=True)
                    for x in f.iterdir():
                        if not (dd / x.name).exists():
                            x.rename(dd / x.name)
        for k, ls in lines.items():
            if ls:
                tmp = ph / (k + ".tmp")
                tmp.write_text("\n".join(ls) + "\n", encoding="utf-8")
                tmp.replace(ph / k)
        for k, d in dicts.items():
            if d:
                tmp = ph / (k + ".tmp")
                tmp.write_text(json.dumps(d, indent=2 if k == REVIEW else None, ensure_ascii=False), encoding="utf-8")
                tmp.replace(ph / k)

        # 5. folders left empty
        for d in sorted((x for x in ph.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
            try:
                d.rmdir()
            except OSError:
                pass
        print(f"  done: {moved} renamed into {ph.name}\\  (log: _rename_log.csv)")
    if not args.go and total:
        print(f"\n{total} photo(s) would be renamed. Nothing changed yet: add  --go  to do it.")
    elif not total:
        print("\nEverything is already organized.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "check", "recheck", "publish", "status", "pack", "merge", "kit", "organize"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", required=(name != "kit"), help="folder that holds the batch folders")
        sp.add_argument("--start-list", help="txt (one bib per line) or csv with a 'bib' column")
        sp.add_argument("--prefill-at", type=float, default=0.5, help="auto-accept reads at or above this confidence")
        if name in ("check", "recheck"):
            sp.add_argument("--model", default=os.environ.get("MARATHON_HAIKU_MODEL", "claude-haiku-5-5"))
            sp.add_argument("--workers", type=int, default=8 if name == "check" else 4, help="parallel photos")
            sp.add_argument("--limit", type=int, help="only the first N photos (try a sample)")
            sp.add_argument("--dry-run", action="store_true", help="count and estimate cost only")
        if name == "recheck":
            sp.add_argument("--eval", action="store_true",
                            help="run on photos people already reviewed and report how much it helps")
            sp.add_argument("--cpu", action="store_true")
        if name == "pack":
            sp.add_argument("--batch", help="batch folder under root, e.g. batch1 (not needed when the root holds the photos)")
            sp.add_argument("--out", help="zip path (default <root>/_packs/review_<batch>.zip)")
            sp.add_argument("--size", type=int, default=1600, help="long side of the photo copies")
            sp.add_argument("--all", action="store_true", help="every photo, not only the ones that need a person")
            sp.add_argument("--no-kit", action="store_true", help="leave the portable Python out (smaller zip)")
        if name == "merge":
            sp.add_argument("--file", required=True, help="the review_<batch>.json you got back")
            sp.add_argument("--batch", help="batch folder name (default: found from the file)")
        if name == "organize":
            sp.add_argument("--prefix", default="ZgMaraton26", help="start of every photo name")
            sp.add_argument("--go", action="store_true", help="really rename (without it: only show the plan)")
            sp.add_argument("--by-name", action="store_true",
                            help="number new photos by file name instead of the time they were taken")
        if name == "scan":
            sp.add_argument("--imgsz", type=int, default=1280)
            sp.add_argument("--det-conf", type=float, default=0.25)
            sp.add_argument("--expand", type=float, default=0.15, help="crop margin around each box")
            sp.add_argument("--cpu", action="store_true")
            sp.add_argument("--no-tiles", action="store_true", help="search the whole photo only (faster, misses small bibs)")
            sp.add_argument("--rescan", action="store_true",
                            help="read already scanned photos again (keeps Haiku results and reviews)")
        if name == "publish":
            sp.add_argument("--event", default="zagreb-2026")
            sp.add_argument("--photographer")
            sp.add_argument("--export-only", action="store_true", help="only write _publish/bib_export.csv")
            sp.add_argument("--skip-photos", action="store_true", help="tags only, photos already uploaded")
            sp.add_argument("--no-rebuild", action="store_true", help="do not trigger the site rebuild")
    args = ap.parse_args()
    return {"scan": cmd_scan, "check": cmd_check, "publish": cmd_publish, "status": cmd_status,
            "pack": cmd_pack, "merge": cmd_merge, "recheck": cmd_recheck, "kit": cmd_kit, "organize": cmd_organize}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
