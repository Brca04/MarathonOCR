"""Move photos whose CSV row has no bib numbers into <folder>\\.excluded\\
so they are never uploaded or served.

Both raceday.py and publish-photos.mjs skip folders whose name starts with
a dot, so moved photos drop out of publish completely. Nothing is deleted;
move them back to undo (or run with --undo).

  python scripts\\exclude_empty.py --root "<photographer folder>" --file davor.csv          (dry run)
  python scripts\\exclude_empty.py --root "<photographer folder>" --file davor.csv --go     (move)
  python scripts\\exclude_empty.py --root "<photographer folder>" --undo --go               (put back)
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

EXCL = ".excluded"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--file", help="reviewer CSV (image_name,bib_numbers)")
    ap.add_argument("--go", action="store_true", help="actually move (default is a dry run)")
    ap.add_argument("--undo", action="store_true", help="move everything in .excluded back")
    a = ap.parse_args()

    root = Path(a.root)
    dest = root / EXCL

    if a.undo:
        files = sorted(dest.glob("*")) if dest.exists() else []
        files = [f for f in files if f.is_file() and f.suffix.lower() != ".csv"]
        print(f"{len(files)} photo(s) to move back from {dest}")
        if a.go:
            for f in files:
                shutil.move(str(f), str(root / f.name))
            print("moved back")
        else:
            print("dry run: add --go to move")
        return 0

    if not a.file:
        sys.exit("--file is required (unless --undo)")
    csv_path = Path(a.file)
    if not csv_path.is_absolute() and not csv_path.exists():
        csv_path = root / csv_path

    empty, missing, total = [], [], 0
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            total += 1
            name = (row.get("image_name") or "").strip()
            nums = [t for t in (row.get("bib_numbers") or "").replace(";", ",").split(",") if t.strip()]
            if name and not nums:
                (empty if (root / name).exists() else missing).append(name)

    print(f"{total} CSV rows, {len(empty)} empty -> {EXCL}\\"
          + (f", {len(missing)} empty row(s) whose photo is not in the folder (already moved?)" if missing else ""))
    for n in empty[:10]:
        print("  ", n)
    if len(empty) > 10:
        print(f"   ... and {len(empty) - 10} more")

    if not a.go:
        print("dry run: add --go to move")
        return 0

    dest.mkdir(exist_ok=True)
    for n in empty:
        shutil.move(str(root / n), str(dest / n))
    with open(dest / "_excluded.csv", "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        for n in empty:
            w.writerow([n])
    print(f"moved {len(empty)} photo(s) to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
