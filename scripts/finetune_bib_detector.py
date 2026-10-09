#!/usr/bin/env python3
"""Fine-tune the bib detector on our own race photos (Željava), starting from
the current models/bib_detector/best.pt, and save the result as best_v3.pt.
The current best.pt is never overwritten.

    python scripts/finetune_bib_detector.py --build-only     # just write the dataset
    python scripts/finetune_bib_detector.py                  # build + train (GPU)

Where the labels come from
--------------------------
The answer key (data/answer_keys/zeljava-2026.csv) says which bibs are in each
photo, but not where. The earlier best.pt run (runs/zeljava_bestpt.jsonl) has a
box and a reading for everything it found. A box whose reading is a bib the key
lists for that photo is a confirmed bib box.

Only photos where EVERY bib in the key got a confirmed box are used for
training. A photo with an unlabelled bib would teach the model to ignore it.
Photos the key marks as having no bibs are added as background examples.

Hand-drawn boxes: put YOLO .txt label files in data/zeljava_manual_labels/
(same file stem as the photo). Those photos are then used too, with the hand
labels taking precedence. That is how the ~150 partly-found photos get in.

Honest scoring: photos are split train/val in blocks of 20 consecutive photos
(bursts of the same runner stay on one side). Every 5th block is validation.
The split is written to data/finetune_zeljava/split.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "src" / "slike" / "zeljava"
KEY = ROOT / "data" / "answer_keys" / "zeljava-2026.csv"
RUN = ROOT / "runs" / "zeljava_bestpt.jsonl"
MANUAL = ROOT / "data" / "zeljava_manual_labels"
OUT = ROOT / "data" / "finetune_zeljava"
ROBOFLOW = ROOT / "src" / "bib number labeling.v14i.yolov11"
BASE_WEIGHTS = ROOT / "models" / "bib_detector" / "best.pt"
DEST_WEIGHTS = ROOT / "models" / "bib_detector" / "best_v3.pt"
OTHER_BOX_CONF = 0.30
LONG_EDGE = 1920  # photos are copied downscaled; YOLO labels are relative, so they still fit


def norm(b: str) -> str:
    return "".join(c for c in str(b) if c.isdigit()).lstrip("0")


def photo_no(name: str) -> int | None:
    m = re.search(r"(\d+)\.[A-Za-z]+$", unicodedata.normalize("NFC", name))
    return int(m.group(1)) if m else None


def load_key() -> dict[int, set[str]]:
    key: dict[int, set[str]] = {}
    with KEY.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            n = photo_no(row["image_name"])
            if n is not None:
                key[n] = {norm(b) for b in (row.get("bib_numbers") or "").split(",") if norm(b)}
    return key


def iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def build(seed: int = 7, negatives: int = 120, roboflow_sample: int = 3000) -> Path:
    from PIL import Image, ImageOps

    if not PHOTOS.exists():
        raise SystemExit(f"photos not found: {PHOTOS}")
    key = load_key()
    runs = {photo_no(r["file"]): r for r in map(json.loads, RUN.read_text(encoding="utf-8").splitlines()) if r}
    files = {photo_no(p.name): p for p in PHOTOS.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}}

    labelled: dict[int, list[list[float]]] = {}  # photo -> [[x0,y0,x1,y1] in pixels], or [] for background
    stats = {"auto_full": 0, "manual": 0, "partial_skipped": 0, "background": 0}
    for n, bibs in key.items():
        if n not in files:
            continue
        manual = MANUAL / (files[n].stem + ".txt")
        if manual.exists():
            labelled[n] = ["manual", manual]  # type: ignore[list-item]
            stats["manual"] += 1
            continue
        if not bibs:
            continue  # backgrounds are sampled below
        r = runs.get(n)
        if not r:
            continue
        boxes: dict[str, list[float]] = {}
        for h in r["hits"]:
            t = norm(h["text"])
            if t in bibs and (t not in boxes or h["conf"] > boxes[t][4]):
                boxes[t] = [*h["bbox"], h["conf"]]
        if set(boxes) == bibs:
            # one box per bib; drop near-duplicates of the same physical bib
            uniq: list[list[float]] = []
            for b in boxes.values():
                if all(iou(b, u) < 0.5 for u in uniq):
                    uniq.append(b[:4])
            # Every other box the old model was fairly sure about is a bib too,
            # just one nobody could read (distant, small, blurred). Leaving those
            # out taught v2 to ignore small bibs, so they are labelled as well.
            for h in r["hits"]:
                b = h["bbox"]
                if h.get("det_conf", 0) >= OTHER_BOX_CONF and all(iou(b, u) < 0.5 for u in uniq):
                    uniq.append(b[:4])
            labelled[n] = uniq
            stats["auto_full"] += 1
        else:
            stats["partial_skipped"] += 1

    rnd = random.Random(seed)
    # Background only where the key has no bibs AND the old model saw no box at
    # all: "no bibs in the key" also covers drone shots full of unreadable bibs.
    empty = [n for n, b in key.items()
             if not b and n in files and n not in labelled and runs.get(n, {}).get("regions", 1) == 0]
    for n in rnd.sample(empty, min(negatives, len(empty))):
        labelled[n] = []
        stats["background"] += 1

    if OUT.exists():
        shutil.rmtree(OUT)
    split = {"train": [], "val": []}
    for n in sorted(labelled):
        part = "val" if (n - 1) // 20 % 5 == 4 else "train"
        split[part].append(files[n].name)
        src = files[n]
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            W, H = im.size
            scale = min(1.0, LONG_EDGE / max(W, H))
            if scale < 1:
                im = im.resize((round(W * scale), round(H * scale)))
            (OUT / "images" / part).mkdir(parents=True, exist_ok=True)
            (OUT / "labels" / part).mkdir(parents=True, exist_ok=True)
            stem = f"zeljava_{n:04d}"
            im.save(OUT / "images" / part / f"{stem}.jpg", quality=92)
        lab = labelled[n]
        if lab and lab[0] == "manual":
            text = Path(lab[1]).read_text(encoding="utf-8")
        else:
            lines = []
            for x0, y0, x1, y1 in lab:
                lines.append(f"0 {(x0 + x1) / 2 / W:.6f} {(y0 + y1) / 2 / H:.6f} {(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}")
            text = "\n".join(lines) + ("\n" if lines else "")
        (OUT / "labels" / part / f"{stem}.txt").write_text(text, encoding="utf-8")

    (OUT / "split.json").write_text(json.dumps(split, indent=1, ensure_ascii=False), encoding="utf-8")
    # Training list: a random sample of the generic Roboflow bibs (so the model
    # keeps what it knew) plus our own photos twice (so they count). Using all
    # ~7,800 Roboflow images made one epoch take 8 minutes.
    rf = sorted((ROBOFLOW / "train" / "images").glob("*.jpg"))
    rf = rnd.sample(rf, min(roboflow_sample, len(rf)))
    ours = sorted((OUT / "images" / "train").glob("*.jpg"))
    train_list = OUT / "train.txt"
    train_list.write_text("\n".join(p.as_posix() for p in rf + ours + ours) + "\n", encoding="utf-8")
    yaml_path = OUT / "data.yaml"
    yaml_path.write_text(
        "\n".join([
            f"train: {train_list.as_posix()}",
            f"val: {(OUT / 'images' / 'val').as_posix()}",
            "nc: 1",
            "names: ['bib-number']",
            "",
        ]),
        encoding="utf-8",
    )
    print("Željava photos used:", stats)
    print(f"train {len(split['train'])} / val {len(split['val'])} photos -> {OUT}")
    print(f"training list: {len(rf)} Roboflow + {len(ours)} Željava (x2)")
    return yaml_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--build-only", action="store_true")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--device", default="0")
    args = p.parse_args()

    data_yaml = build()
    if args.build_only:
        return 0

    from ultralytics import YOLO

    model = YOLO(str(BASE_WEIGHTS))
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        lr0=0.002,           # gentle: we are adjusting a trained model, not starting over
        patience=10,
        workers=2,           # Windows: 8 dataloader workers crashed ("Pin memory thread exited")
        project=str(ROOT / "runs" / "bib_detector"),
        name="finetune_zeljava_v3",
        exist_ok=True,
    )
    best = Path(results.save_dir) / "weights" / "best.pt"
    if not best.exists():
        print(f"no weights at {best}", file=sys.stderr)
        return 1
    shutil.copyfile(best, DEST_WEIGHTS)
    print(f"\nsaved {DEST_WEIGHTS}  (the old best.pt is unchanged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
