#!/usr/bin/env python3
"""Turn existing OCR results into pre-filled suggestions for review_app.py.

The review app then opens instantly (no model re-run): each photo shows the
model's reads as boxes, and the confirmed-numbers list is pre-filled with the
reads that are (a) confident enough and (b) real bibs on the start list.
Everything you save in the app becomes the answer key for testing other
recognizers.

    python scripts/make_suggestions.py --photos src/slike \
        --ocr _transfer/ocr_all.jsonl --meta _transfer/meta.csv \
        --start-list _transfer/zeljava/load.json
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

OUT_NAME = ".marathon_ocr_suggestions.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--meta", help="CSV file,original_name when OCR used renamed files")
    ap.add_argument("--start-list", help="load.json (runners[].bib) or a CSV with a 'bib' column")
    ap.add_argument("--prefill-at", type=float, default=0.5,
                    help="pre-fill reads at or above this confidence (default 0.5)")
    args = ap.parse_args()

    names = {}
    if args.meta:
        names = {r["file"]: r["original_name"] for r in csv.DictReader(open(args.meta, encoding="utf-8"))}

    valid: set[str] | None = None
    if args.start_list:
        p = Path(args.start_list)
        if p.suffix == ".json":
            valid = {str(r["bib"]) for r in json.loads(p.read_text(encoding="utf-8"))["runners"]}
        else:
            valid = {r["bib"].strip() for r in csv.DictReader(open(p, encoding="utf-8"))}

    out = {}
    for line in open(args.ocr, encoding="utf-8"):
        d = json.loads(line)
        name = names.get(d["file"], d["file"])
        best: dict[str, dict] = {}
        for h in d["hits"]:
            t = h["text"].lstrip("0") or "0"
            if t not in best or h["conf"] > best[t]["conf"]:
                best[t] = dict(h, text=t)
        persons, numbers = [], []
        for t, h in sorted(best.items(), key=lambda kv: -kv[1]["conf"]):
            real = valid is None or t in valid
            if h["conf"] < 0.1:
                continue
            take = real and h["conf"] >= args.prefill_at
            if take:
                numbers.append(t)
            persons.append(dict(
                box=h["bbox"], ocr=[[t, h["conf"]]], unsure=not take,
                verdict="confident" if take else "model_only", needs_human=True,
                haiku=None, on_start_list=real))
        out[name] = dict(numbers=numbers, needs_human=1, persons=persons, source="ocr")

    dest = Path(args.photos) / OUT_NAME
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    filled = sum(1 for v in out.values() if v["numbers"])
    print(f"{len(out)} photos, {filled} with pre-filled numbers -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
