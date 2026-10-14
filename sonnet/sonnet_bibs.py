#!/usr/bin/env python3
"""Sonnet bib reader: a separate, accuracy-first pipeline (no YOLO, no EasyOCR).

Every photo goes through up to five steps. Each step only does what the one
before could not:

  1. survey   Sonnet looks at the whole photo at full resolution and lists every
              bib it sees, with a box, even the ones it cannot read.
  2. tiles    For crowded or doubtful photos: four overlapping quarters, enlarged,
              each read the same way. Finds small bibs in the background.
  3. zoom     Every bib found is cut out of the original at full resolution,
              enlarged, and read again on its own: once with the runner around it
              (bib outlined), once as a tight close-up. No earlier reading is shown,
              so this is an independent second opinion.
  4. judge    Only where the readings disagree: Sonnet thinks it over with both
              earlier readings and two fresh crops, and decides.
  5. resolve  Offline, free: neighbouring frames (bursts) complete half-hidden
              bibs ("23?5" next to frames that clearly show 2315), and the start
              list (optional) removes numbers that cannot exist.

A bib is accepted only when independent readings agree (or the judge is sure);
anything else goes to the review app, with the candidates pre-filled.

Layout is the same as raceday.py: a root folder, one folder per photographer.
Everything this pipeline writes lives in a hidden  .sonnet  folder inside each
photographer folder, so the old pipeline's files are never touched.

    python sonnet/sonnet_bibs.py estimate --root D:\\ZG26                 # cost, no API calls
    python sonnet/sonnet_bibs.py run      --root D:\\ZG26 --reviewed --limit 100   # trial on photos people checked
    python sonnet/sonnet_bibs.py eval     --root D:\\ZG26                 # accuracy vs people (and vs the old pipeline)
    python sonnet/sonnet_bibs.py run      --root D:\\ZG26 --batch         # everything, Batch API (half price)
    python sonnet/sonnet_bibs.py review   --root D:\\ZG26                 # load results into review_desktop.py
    python sonnet/sonnet_bibs.py export   --root D:\\ZG26                 # _publish_sonnet/bib_export.csv
    python sonnet/sonnet_bibs.py status   --root D:\\ZG26

Safe to stop and re-run at any point: finished work is kept, only what is
missing is sent. Needs ANTHROPIC_API_KEY in MarathonOCR/.env, plus anthropic and
Pillow (both already in the repo's .venv).
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import math
import os
import random
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent  # the MarathonOCR repo
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
STATE = ".sonnet"
REVIEW = ".marathon_ocr_review.json"          # what people confirmed (review app), never written here
SUGGESTIONS = ".marathon_ocr_suggestions.json"  # what the review app pre-fills
OLD_SUGGESTIONS_BACKUP = ".marathon_ocr_suggestions.raceday.json"

MODEL = os.environ.get("SONNET_MODEL", "claude-sonnet-5-5")
# USD per million tokens (input, output), standard API. Batch API is half of this.
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

# Claude 4.7+ vision ("high-resolution tier"): an image costs ceil(w/28)*ceil(h/28)
# tokens, at most 4784, long edge at most 2576 px. Images that fit are not resized,
# so box coordinates come back in our own pixels.
MAX_EDGE, MAX_IMG_TOKENS, PATCH = 2576, 4784, 28


def img_tokens(w: int, h: int) -> int:
    return math.ceil(w / PATCH) * math.ceil(h / PATCH)


def fit_size(w: int, h: int, max_factor: float = 8.0) -> tuple[int, int]:
    """Largest size (aspect kept, scale <= max_factor) that the model sees unresized."""
    lo, hi = 0.05, max_factor
    if _fits(w, h, hi):
        return max(1, round(w * hi)), max(1, round(h * hi))
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _fits(w, h, mid) else (lo, mid)
    return max(1, int(w * lo)), max(1, int(h * lo))


def _fits(w, h, f) -> bool:
    W, H = max(1, round(w * f)), max(1, round(h * f))
    return max(W, H) <= MAX_EDGE and img_tokens(W, H) <= MAX_IMG_TOKENS


# --------------------------------------------------------------------------- prompts

SYSTEM = """You read race bib numbers in photos from running races, for a site where runners find their own photos by bib number. A wrong number shows a stranger's photo to someone; a missed number hides a runner's photo. Both matter, so be exact and honest about what you can and cannot see.

What a bib is: a printed card (paper or Tyvek) pinned to a runner's chest, stomach or back, or on a race belt. It carries one large main number. Bibs fold, crease, flap, tilt and twist; arms, hands, bottles, phones, jackets and other runners often cover part of them.

Read ONLY the large main number of each bib. Ignore everything else, even when it contains digits: small text on the bib (names, age categories such as M35 or W40, distance, wave, year, sponsor names, QR or barcodes, timing-chip numbers), shirt and vest prints, country names, the event name or edition ("34."), race clocks and timers, signs, banners, arches, cars and number plates.

Digits:
- Report digits exactly as printed, left to right. Do not drop or add digits.
- Use "?" for each digit position you can see is there but cannot read.
- If part of the number may be hidden (folded, covered, or outside the picture), say which side may be missing digits in "cut". Never fill hidden digits with a guess.
- Common confusions to check carefully: 1/7, 3/8, 5/6, 6/8, 0/8, 1/4, 2/7, 9/8. A crease or shadow is not a digit.

"legibility":
- "clear": every digit is plainly readable and none can be missing.
- "partial": you can read some or all digits but are not certain of every one, or digits may be hidden.
- "unreadable": you can see a bib but cannot read its number.

Reply with JSON only, matching the requested format."""

SURVEY = """This is a full race photo, {w} x {h} pixels.

Find EVERY race bib in the photo: runners in front and in the background, small, blurred, tilted, folded or half-hidden bibs, and bibs you cannot read at all. Scan the whole image systematically (left to right, front to back) before answering; crowded scenes can hold 30 or more bibs.

For each bib give:
- "box": [x1, y1, x2, y2], the bib's bounding box in pixel coordinates of this image (top-left and bottom-right corners; x to the right, y down, origin top-left).
- "number": the main number as described ("" if unreadable).
- "legibility": "clear", "partial" or "unreadable".
- "cut": "none" if the whole number is visible, else "left", "right", "both" or "unknown".

Reply as {{"bibs": [...]}}, ordered left to right."""

TILE = """This is an enlarged part of a race photo ({w} x {h} pixels as shown here). Bibs may be cut by the edge of this part; mark those with "cut".

""" + SURVEY.split("\n\n", 1)[1]

ZOOM = """Below are {n} bib(s) from one race photo, each shown twice:
  (a) the bib with the runner around it; the bib to read is outlined by a thin magenta frame (the frame is not part of the bib),
  (b) a close-up of the same bib, enlarged.
Read each bib on its own. If the outlined thing is not a race bib (a shirt print, sign, logo, arm, etc.) set "is_bib" to false. If several bibs are visible, read only the outlined one.

For each bib give:
- "id": the bib's number in this list,
- "is_bib": true or false,
- "number": the main number ("" if unreadable), "?" for each unreadable digit,
- "legibility": "clear", "partial" or "unreadable",
- "cut": "none", "left", "right", "both" or "unknown" (could digits be hidden?),
- "alternatives": other numbers it could plausibly be, most likely first (empty if "clear").

Reply as {{"bibs": [...]}}."""

JUDGE = """Two independent readings of the same bib disagree. Decide what the bib really says.

Earlier readings (they can be wrong, or both wrong):
{readings}

Image (a): the bib with the runner around it, outlined by a thin magenta frame (not part of the bib).
Image (b): a close-up of the bib, enlarged.
Image (c): the same close-up, sharpened.

Look at every digit position one by one, checking the usual confusions (1/7, 3/8, 5/6, 6/8, 0/8, 1/4, 2/7, 9/8) and whether a fold, arm or edge could hide a digit. Then give your final reading:
- "is_bib": true or false,
- "number": the main number, "?" for each digit you cannot read,
- "legibility": "clear" only if you are certain of every digit and none can be missing; else "partial" or "unreadable",
- "cut": "none", "left", "right", "both" or "unknown",
- "reason": one short sentence.

Reply as one JSON object."""

LEG = {"type": "string", "enum": ["clear", "partial", "unreadable"]}
CUT = {"type": "string", "enum": ["none", "left", "right", "both", "unknown"]}
SURVEY_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["bibs"],
    "properties": {"bibs": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["box", "number", "legibility", "cut"],
        "properties": {"box": {"type": "array", "items": {"type": "integer"}},
                       "number": {"type": "string"}, "legibility": LEG, "cut": CUT}}}},
}
ZOOM_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["bibs"],
    "properties": {"bibs": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "is_bib", "number", "legibility", "cut", "alternatives"],
        "properties": {"id": {"type": "integer"}, "is_bib": {"type": "boolean"},
                       "number": {"type": "string"}, "legibility": LEG, "cut": CUT,
                       "alternatives": {"type": "array", "items": {"type": "string"}}}}}},
}
JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["is_bib", "number", "legibility", "cut", "reason"],
    "properties": {"is_bib": {"type": "boolean"}, "number": {"type": "string"}, "legibility": LEG,
                   "cut": CUT, "reason": {"type": "string"}},
}

# --------------------------------------------------------------------------- settings


@dataclass
class Settings:
    model: str = MODEL
    judge_model: str = MODEL
    tiles: str = "auto"            # off | auto | always
    tile_min_bibs: int = 4          # auto: crowded photo
    think: str = "medium"           # thinking effort for survey/tiles/zoom: off | low | medium | high
    judge_think: str = "high"
    schema: bool = True             # structured outputs (guaranteed JSON)
    zoom_per_call: int = 6
    burst_window: int = 6           # frames either side
    start: set[str] | None = None

    def thinking(self, effort: str) -> dict:
        if effort == "off":
            return {}
        return {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}


# --------------------------------------------------------------------------- files


def batches(root: Path) -> list[Path]:
    """Every folder under root (root included) that directly holds photos."""
    out = []
    for d in [root, *sorted(p for p in root.rglob("*") if p.is_dir())]:
        if any(part.startswith((".", "_")) for part in d.relative_to(root).parts):
            continue
        if any(f.suffix.lower() in IMAGE_EXTS and not f.name.startswith(".") for f in d.iterdir()):
            out.append(d)
    return out


def natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def photos_in(folder: Path) -> list[Path]:
    """In shot order (raceday.py organize numbers photos by capture time)."""
    return sorted((f for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXTS and not f.name.startswith(".")),
                  key=lambda p: natural(p.name))


def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(p: Path, data, indent=None) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(p)


class Store:
    """Append-only JSONL per folder and step; the last line for a key wins."""

    _lock = threading.Lock()

    def __init__(self, folder: Path, step: str):
        self.path = folder / STATE / f"{step}.jsonl"
        self.rows: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # a line cut off by a crash
                    self.rows[r["key"]] = r

    def get(self, key: str) -> dict | None:
        r = self.rows.get(key)
        return r if r and not r.get("error") else None

    def put(self, row: dict) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.rows[row["key"]] = row


def load_env() -> None:
    for env in (ROOT / ".env", Path.cwd() / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_start_list(path: str | None) -> set[str] | None:
    if not path:
        return None
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    if p.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        col = next((c for c in (rows[0].keys() if rows else []) if c.strip().lower() in
                    ("bib", "startni_broj", "startni broj", "broj", "start_no", "number", "bib_number")), None)
        vals = [r[col] for r in rows] if col else []
    else:
        vals = text.split()
    out = {norm(v) for v in vals} - {""}
    print(f"start list: {len(out)} bibs from {p}")
    return out


# --------------------------------------------------------------------------- images


def open_photo(p: Path) -> Image.Image:
    with Image.open(p) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def b64(img: Image.Image, quality: int = 92) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, subsampling=0)
    return base64.standard_b64encode(buf.getvalue()).decode()


def image_block(img: Image.Image) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(img)}}


def prepare_whole(img: Image.Image) -> tuple[Image.Image, float]:
    """The photo as the model will see it, unresized by the API: (image, scale)."""
    W, H = fit_size(*img.size, max_factor=1.0)
    if (W, H) == img.size:
        return img, 1.0
    return img.resize((W, H), Image.LANCZOS), W / img.width


def tile_rects(W: int, H: int, frac: float = 0.58) -> list[tuple[int, int, int, int]]:
    tw, th = int(W * frac), int(H * frac)
    return [(x, y, x + tw, y + th) for x, y in ((0, 0), (W - tw, 0), (0, H - th), (W - tw, H - th))]


def prepare_tile(img: Image.Image, rect) -> tuple[Image.Image, float]:
    tile = img.crop(rect)
    W, H = fit_size(*tile.size, max_factor=2.5)
    return tile.resize((W, H), Image.LANCZOS), W / tile.width


def clamp_box(b, W, H):
    x0, y0, x1, y1 = (float(v) for v in b)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    return [max(0.0, min(W, x0)), max(0.0, min(H, y0)), max(0.0, min(W, x1)), max(0.0, min(H, y1))]


def zoom_images(img: Image.Image, box, context: float = 1.0, target: int = 768) -> tuple[Image.Image, Image.Image]:
    """(a) bib with runner around it, outlined; (b) tight close-up. Both enlarged."""
    W, H = img.size
    x0, y0, x1, y1 = box
    bw, bh = max(8.0, x1 - x0), max(8.0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # Context: about 2x the bib wide and 3x high (torso, arms), at least 96 px.
    cw = max(bw * 2.2 * context, bh * 3.0 * context, 96)
    ch = max(bh * 3.0 * context, bw * 1.5 * context, 96)
    a = (max(0, cx - cw / 2), max(0, cy - ch / 2), min(W, cx + cw / 2), min(H, cy + ch / 2))
    ctx = img.crop(tuple(round(v) for v in a))
    f = min(6.0, max(1.0, target / max(ctx.size)))
    ctx = ctx.resize((max(1, round(ctx.width * f)), max(1, round(ctx.height * f))), Image.LANCZOS)
    d = ImageDraw.Draw(ctx)
    pad = max(4, 0.06 * bh * f)
    r = ((x0 - a[0]) * f - pad, (y0 - a[1]) * f - pad, (x1 - a[0]) * f + pad, (y1 - a[1]) * f + pad)
    d.rectangle(r, outline=(255, 0, 255), width=max(2, round(f)))
    # Close-up: the bib plus a margin for digits the box may have cut.
    mx, my = bw * 0.18 + 4, bh * 0.25 + 4
    t = (max(0, x0 - mx), max(0, y0 - my), min(W, x1 + mx), min(H, y1 + my))
    tight = img.crop(tuple(round(v) for v in t))
    f2 = min(8.0, max(1.0, target / max(tight.size)))
    tight = tight.resize((max(1, round(tight.width * f2)), max(1, round(tight.height * f2))), Image.LANCZOS)
    return ctx, tight


def sharpen(img: Image.Image) -> Image.Image:
    return ImageOps.autocontrast(img.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=2)), cutoff=1)


# --------------------------------------------------------------------------- reads


def norm(t: str) -> str:
    return "".join(ch for ch in str(t) if ch.isdigit()).lstrip("0")


def clean_number(t: str) -> str:
    """Digits and '?', nothing else; leading zeros dropped (bib 0042 is 42)."""
    s = "".join(ch for ch in str(t) if ch.isdigit() or ch == "?")
    s = s.lstrip("0") if not s.startswith("0?") else s
    return s[:7]


@dataclass
class Read:
    source: str
    number: str
    legibility: str
    cut: str = "unknown"
    is_bib: bool = True
    alternatives: list[str] = field(default_factory=list)

    @property
    def full(self) -> str | None:
        """A complete number: digits only, nothing possibly hidden, readable."""
        if not self.is_bib or self.legibility == "unreadable" or not self.number or "?" in self.number:
            return None
        if self.cut not in ("none",) and self.legibility != "clear":
            return None
        return self.number

    @property
    def clear(self) -> bool:
        return self.full is not None and self.legibility == "clear" and self.cut == "none"

    def as_dict(self):
        return dict(source=self.source, number=self.number, legibility=self.legibility, cut=self.cut,
                    is_bib=self.is_bib, alternatives=self.alternatives)


def to_read(source: str, d: dict) -> Read:
    return Read(source=source, number=clean_number(d.get("number", "")),
                legibility=d.get("legibility") if d.get("legibility") in ("clear", "partial", "unreadable") else "partial",
                cut=d.get("cut") if d.get("cut") in ("none", "left", "right", "both", "unknown") else "unknown",
                is_bib=bool(d.get("is_bib", True)),
                alternatives=[a for a in (clean_number(x) for x in d.get("alternatives") or []) if a][:4])


def parse_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S) or re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON in reply: {text[:120]!r}")
    return json.loads(m.group(1) if m.lastindex else m.group(0))


# --------------------------------------------------------------------------- candidates


def iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def same_bib(a, b) -> bool:
    if iou(a, b) >= 0.25:
        return True
    # Model boxes wobble: centre of one inside the other, and similar size.
    for p, q in ((a, b), (b, a)):
        cx, cy = (p[0] + p[2]) / 2, (p[1] + p[3]) / 2
        if q[0] <= cx <= q[2] and q[1] <= cy <= q[3]:
            ap, aq = (p[2] - p[0]) * (p[3] - p[1]), (q[2] - q[0]) * (q[3] - q[1])
            if min(ap, aq) / max(ap, aq, 1e-6) >= 0.2:
                return True
    return False


def box_key(b) -> str:
    return ",".join(str(round(v)) for v in b)


@dataclass
class Cand:
    box: list[float]
    reads: list[Read]

    @property
    def key(self) -> str:
        return box_key(self.box)


def candidates(survey: dict, tiles: list[dict]) -> list[Cand]:
    """Every bib seen by the survey or a tile, merged by position."""
    items = []  # (box, read, priority): tiles are enlarged, so their boxes are tighter
    for b in survey.get("bibs", []):
        items.append((b["box"], to_read("survey", b), 0))
    for t in tiles:
        for b in t.get("bibs", []):
            items.append((b["box"], to_read(f"tile{t['tile']}", b), 1))
    clusters: list[list] = []
    for it in items:
        for c in clusters:
            if any(same_bib(it[0], o[0]) for o in c):
                c.append(it)
                break
        else:
            clusters.append([it])
    out = []
    for c in clusters:
        # The box from the read that saw the most of the bib: clear > partial, uncut > cut, tile > survey.
        best = max(c, key=lambda it: (it[1].legibility == "clear", it[1].cut == "none", it[2],
                                      (it[0][2] - it[0][0]) * (it[0][3] - it[0][1])))
        if best[1].cut != "none":
            # A bib cut by a tile edge: the union of boxes covers the whole bib.
            box = [min(o[0][0] for o in c), min(o[0][1] for o in c), max(o[0][2] for o in c), max(o[0][3] for o in c)]
        else:
            box = list(best[0])
        out.append(Cand([round(v, 1) for v in box], [o[1] for o in c]))
    out.sort(key=lambda c: (c.box[0], c.box[1]))
    return out


# --------------------------------------------------------------------------- decision


def pattern_match(pattern: str, number: str) -> bool:
    return len(pattern) == len(number) and all(p in ("?", n) for p, n in zip(pattern, number))


def decide(c: Cand, zoom: Read | None, judge: Read | None) -> dict:
    """One bib -> accept / judge / review / drop."""
    reads = c.reads + ([zoom] if zoom else []) + ([judge] if judge else [])
    if zoom and not zoom.is_bib and not (judge and judge.is_bib):
        clear_others = Counter(r.full for r in c.reads if r.clear)
        if not clear_others or clear_others.most_common(1)[0][1] < 2:
            return dict(status="drop", why="not a bib")
    if judge:
        if not judge.is_bib:
            return dict(status="drop", why="judge: not a bib")
        earlier = {r.full for r in c.reads + ([zoom] if zoom else []) if r.full}
        if judge.full and (judge.legibility == "clear" or judge.full in earlier):
            return dict(status="accept", number=judge.full, how="judge")
        cands = ([judge.full] if judge.full else []) + [n for n, _ in Counter(
            r.full for r in reads if r.full).most_common() if n != judge.full]
        return dict(status="review", candidates=cands, pattern=best_pattern(reads), why="judge unsure")
    fulls = Counter(r.full for r in reads if r.full)
    if zoom and zoom.full:
        others = {r.full for r in c.reads if r.full}
        if zoom.clear and others <= {zoom.full}:
            return dict(status="accept", number=zoom.full, how="zoom clear" + (", agreed" if others else ""))
        if zoom.full in others and len(others) == 1:
            return dict(status="accept", number=zoom.full, how="two readings agree")
    if fulls:
        return dict(status="judge", candidates=[n for n, _ in fulls.most_common()])
    pat = best_pattern(reads)
    if pat and sum(ch != "?" for ch in pat) >= 1:
        return dict(status="review", candidates=[], pattern=pat, why="digits hidden")
    return dict(status="drop", why="unreadable")


def best_pattern(reads: list[Read]) -> str:
    """The most informative partial reading ('23?5'), zoom/judge first."""
    order = {"judge": 0, "zoom": 1}
    rs = sorted((r for r in reads if r.is_bib and r.number and r.legibility != "unreadable"),
                key=lambda r: (order.get(r.source, 2), -sum(ch != "?" for ch in r.number)))
    return rs[0].number if rs else ""


def resolve_folder(entries: dict[str, dict], order: list[str], st: Settings) -> None:
    """Free, offline: bursts and the start list settle what the readings could not.

    entries[name]["bibs"] is a list of decisions (see decide). Modified in place.
    """
    accepted = {n: {b["number"] for b in e["bibs"] if b["status"] == "accept"} for n, e in entries.items()}
    pos = {n: i for i, n in enumerate(order)}
    for name, e in entries.items():
        i = pos.get(name)
        near: Counter = Counter()
        if i is not None:
            for j in range(max(0, i - st.burst_window), min(len(order), i + st.burst_window + 1)):
                if j != i:
                    near.update(accepted.get(order[j], ()))
        for b in e["bibs"]:
            if b["status"] not in ("review", "judge"):
                continue
            cands = b.get("candidates") or []
            pat = b.get("pattern") or ""
            # 1. Disagreement where exactly one candidate is confirmed in neighbouring frames.
            hit = [n for n in cands if near.get(n)]
            if len(hit) == 1:
                b.update(status="accept", number=hit[0], how="burst: seen clearly in nearby frames")
                continue
            # 2. A pattern with at most one hidden digit, matching exactly one nearby bib.
            if pat and "?" in pat and len(pat) >= 3 and pat.count("?") <= 1:
                m = [n for n in near if pattern_match(pat, n)]
                if len(m) == 1:
                    b.update(status="accept", number=m[0], how=f"burst: {pat} completed from nearby frames")
                    continue
            # 3. Start list: keep only numbers that exist.
            if st.start is not None:
                ok = [n for n in cands if n in st.start]
                if len(ok) == 1 and len(cands) > 1:
                    b.update(status="accept", number=ok[0], how="start list: only valid candidate")
                    continue
                if pat and "?" in pat:
                    m = sorted(n for n in st.start if pattern_match(pat, n))
                    if 0 < len(m) <= 5:
                        b["candidates"] = list(dict.fromkeys(cands + m))
            if b["status"] == "judge":
                b["status"] = "review"
                b.setdefault("why", "readings disagree")
    if st.start is not None:
        for e in entries.values():
            for b in e["bibs"]:
                if b["status"] == "accept" and b["number"] not in st.start:
                    near_valid = sorted(n for n in st.start if len(n) == len(b["number"])
                                        and sum(x != y for x, y in zip(n, b["number"])) == 1)
                    b.update(status="review", candidates=[b["number"]] + near_valid[:4],
                             why="not on the start list")
    for e in entries.values():
        e["numbers"] = list(dict.fromkeys(b["number"] for b in e["bibs"] if b["status"] == "accept"))
        e["needs_human"] = sum(1 for b in e["bibs"] if b["status"] == "review")


# --------------------------------------------------------------------------- API runner


@dataclass
class Job:
    key: str               # unique within a step
    folder: Path
    build: object          # () -> messages.create(**params); built only when sent (images are big)
    meta: dict
    model: str = MODEL


class Spend:
    def __init__(self, cap: float | None):
        self.usd, self.inp, self.out, self.calls, self.cap = 0.0, 0, 0, 0, cap
        self.lock = threading.Lock()

    def add(self, model: str, usage, batch: bool) -> None:
        pin, pout = PRICES.get(model, PRICES["claude-sonnet-5-5"])
        f = 0.5 if batch else 1.0
        i = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25 \
            + (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.05
        o = getattr(usage, "output_tokens", 0) or 0
        with self.lock:
            self.inp += int(i)
            self.out += o
            self.calls += 1
            self.usd += f * (i * pin + o * pout) / 1e6

    @property
    def over(self) -> bool:
        return self.cap is not None and self.usd >= self.cap


def message_text(msg) -> str:
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")


class Runner:
    def __init__(self, args, spend: Spend):
        self.args, self.spend = args, spend
        self.batch = bool(getattr(args, "batch", False))
        self._client = None

    @property
    def client(self):
        if self._client is None:
            load_env()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit("ANTHROPIC_API_KEY is not set: put ANTHROPIC_API_KEY=sk-ant-... in MarathonOCR/.env")
            import anthropic
            self._client = anthropic.Anthropic(max_retries=8, timeout=600)
        return self._client

    def run(self, step: str, jobs: list[Job], on_result) -> None:
        """on_result(job, parsed_json_or_None, error_or_None, usage)"""
        if not jobs:
            return
        print(f"  {step}: {len(jobs)} request(s) " + ("via Batch API" if self.batch else "live"), flush=True)
        (self._run_batch if self.batch else self._run_live)(step, jobs, on_result)

    # ---- live: parallel requests, results saved as they arrive
    def _run_live(self, step, jobs, on_result):
        t0, n = time.perf_counter(), 0
        stop = threading.Event()

        def one(job: Job):
            if stop.is_set():
                return job, None, "skipped: spending cap reached", None
            try:
                msg = self.client.messages.create(**job.build())
            except Exception as exc:  # noqa: BLE001 - one bad call must not stop the run
                return job, None, f"{type(exc).__name__}: {exc}"[:400], None
            self.spend.add(job.model, msg.usage, False)
            try:
                return job, parse_json(message_text(msg)), None, msg.usage
            except (ValueError, json.JSONDecodeError) as exc:
                return job, None, f"bad reply: {exc}"[:400], msg.usage

        with ThreadPoolExecutor(max_workers=self.args.workers) as pool:
            for fut in as_completed([pool.submit(one, j) for j in jobs]):
                job, data, err, usage = fut.result()
                on_result(job, data, err, usage)
                n += 1
                if self.spend.over and not stop.is_set():
                    stop.set()
                    print(f"  ! spending cap ${self.spend.cap:.2f} reached; stopping (re-run to continue)")
                if n % 25 == 0 or n == len(jobs):
                    print(f"    {n}/{len(jobs)}  ${self.spend.usd:.2f} so far  {time.perf_counter() - t0:.0f}s", flush=True)
        if stop.is_set():
            raise SystemExit(1)

    # ---- batch: half price, results within minutes to hours; resumable
    def _run_batch(self, step, jobs, on_result):
        root = Path(self.args.root).resolve()
        reg_path = root / STATE / "batches.json"
        reg = read_json(reg_path)
        by_key = {j.key: j for j in jobs}
        pending = [b for b in reg.get(step, []) if not b.get("done")]
        submitted_keys = {k for b in pending for k in b["ids"].values()}
        fresh = [j for j in jobs if j.key not in submitted_keys]
        # Chunks: at most 2000 requests or ~150 MB of request data each (the API allows 256 MB).
        def submit(chunk):
            ids = {f"r{i}": k for i, (k, _) in enumerate(chunk)}
            b = self.client.messages.batches.create(
                requests=[{"custom_id": f"r{i}", "params": p} for i, (_, p) in enumerate(chunk)])
            print(f"    submitted batch {b.id} ({len(chunk)} requests)", flush=True)
            reg.setdefault(step, []).append({"id": b.id, "ids": ids, "done": False})
            write_json(reg_path, reg, indent=1)

        chunk, size = [], 0
        for j in fresh:
            p = j.build()
            s = len(json.dumps(p))
            if chunk and (len(chunk) >= 2000 or size + s > 150e6):
                submit(chunk)
                chunk, size = [], 0
            chunk.append((j.key, p))
            size += s
        if chunk:
            submit(chunk)
        del chunk
        todo = [b for b in reg.get(step, []) if not b.get("done")]
        t0 = time.perf_counter()
        while todo:
            for b in list(todo):
                info = self.client.messages.batches.retrieve(b["id"])
                if info.processing_status != "ended":
                    continue
                for res in self.client.messages.batches.results(b["id"]):
                    key = b["ids"].get(res.custom_id)
                    job = by_key.get(key)
                    if job is None:
                        continue  # from an older run whose job is no longer needed
                    if res.result.type == "succeeded":
                        msg = res.result.message
                        self.spend.add(job.model, msg.usage, True)
                        try:
                            on_result(job, parse_json(message_text(msg)), None, msg.usage)
                        except (ValueError, json.JSONDecodeError) as exc:
                            on_result(job, None, f"bad reply: {exc}"[:400], msg.usage)
                    else:
                        err = getattr(res.result, "error", None)
                        on_result(job, None, f"batch {res.result.type}: {err}"[:400], None)
                b["done"] = True
                write_json(reg_path, reg, indent=1)
                todo.remove(b)
                print(f"    batch {b['id']} finished  (${self.spend.usd:.2f} so far)", flush=True)
            if todo:
                waited = time.perf_counter() - t0
                print(f"    waiting for {len(todo)} batch(es)... {waited / 60:.0f} min "
                      "(safe to close; re-run the same command later to collect)", flush=True)
                time.sleep(60)


# --------------------------------------------------------------------------- the steps


def params(st: Settings, model: str, content: list, schema: dict, max_tokens: int, effort: str) -> dict:
    p = {"model": model, "max_tokens": max_tokens,
         "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
         "messages": [{"role": "user", "content": content}]}
    p.update(st.thinking(effort))
    if st.schema:
        p.setdefault("output_config", {})["format"] = {"type": "json_schema", "schema": schema}
    return p


def clean_bibs(raw: dict, scale: float, offset=(0, 0), W=None, H=None) -> list[dict]:
    out = []
    for b in raw.get("bibs") or []:
        box = b.get("box") or []
        if len(box) != 4:
            continue
        box = [offset[0] + box[0] / scale, offset[1] + box[1] / scale,
               offset[0] + box[2] / scale, offset[1] + box[3] / scale]
        box = clamp_box(box, W, H)
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        out.append(dict(box=[round(v, 1) for v in box], number=str(b.get("number", "")),
                        legibility=b.get("legibility", "partial"), cut=b.get("cut", "unknown")))
    return out


class Pipeline:
    def __init__(self, root: Path, photos: list[tuple[Path, Path]], st: Settings, runner: Runner):
        self.root, self.photos, self.st, self.runner = root, photos, st, runner
        self.stores: dict[tuple[Path, str], Store] = {}
        self.sizes: dict[Path, tuple[int, int]] = {}

    def store(self, folder: Path, step: str) -> Store:
        k = (folder, step)
        if k not in self.stores:
            self.stores[k] = Store(folder, step)
        return self.stores[k]

    def size(self, p: Path) -> tuple[int, int]:
        if p not in self.sizes:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im)
                self.sizes[p] = im.size
        return self.sizes[p]

    # 1. survey
    def survey(self):
        jobs = []
        for folder, p in self.photos:
            if self.store(folder, "survey").get(p.name):
                continue
            W, H = self.size(p)
            sw, sh = fit_size(W, H, max_factor=1.0)

            def build(p=p):
                seen, _ = prepare_whole(open_photo(p))
                content = [image_block(seen), {"type": "text", "text": SURVEY.format(w=seen.width, h=seen.height)}]
                return params(self.st, self.st.model, content, SURVEY_SCHEMA, 8000, self.st.think)

            jobs.append(Job(f"{folder.name}/{p.name}", folder, build,
                            dict(photo=p, scale=sw / W, W=W, H=H), self.st.model))
        self.runner.run("survey", jobs, self._save_survey)

    def _save_survey(self, job, data, err, usage):
        m = job.meta
        row = dict(key=m["photo"].name, w=m["W"], h=m["H"], error=err)
        if data is not None:
            row["bibs"] = clean_bibs(data, m["scale"], W=m["W"], H=m["H"])
        self.store(job.folder, "survey").put(row)

    # 2. tiles
    def wants_tiles(self, sv: dict) -> bool:
        if self.st.tiles == "always":
            return True
        if self.st.tiles == "off":
            return False
        bibs = sv.get("bibs", [])
        return (len(bibs) >= self.st.tile_min_bibs or not bibs
                or any(b["legibility"] != "clear" or b["cut"] != "none" for b in bibs))

    def tiles(self):
        jobs = []
        for folder, p in self.photos:
            sv = self.store(folder, "survey").get(p.name)
            if not sv or not self.wants_tiles(sv):
                continue
            for i, rect in enumerate(tile_rects(sv["w"], sv["h"])):
                key = f"{p.name}#{i}"
                if self.store(folder, "tiles").get(key):
                    continue
                tw = rect[2] - rect[0]
                scale = fit_size(tw, rect[3] - rect[1], max_factor=2.5)[0] / tw

                def build(p=p, rect=rect):
                    seen, _ = prepare_tile(open_photo(p), rect)
                    content = [image_block(seen), {"type": "text", "text": TILE.format(w=seen.width, h=seen.height)}]
                    return params(self.st, self.st.model, content, SURVEY_SCHEMA, 8000, self.st.think)

                jobs.append(Job(f"{folder.name}/{key}", folder, build,
                                dict(photo=p, key=key, tile=i, scale=scale, rect=rect, W=sv["w"], H=sv["h"]),
                                self.st.model))
        self.runner.run("tiles", jobs, self._save_tile)

    def _save_tile(self, job, data, err, usage):
        m = job.meta
        row = dict(key=m["key"], photo=m["photo"].name, tile=m["tile"], error=err)
        if data is not None:
            row["bibs"] = clean_bibs(data, m["scale"], offset=m["rect"][:2], W=m["W"], H=m["H"])
        self.store(job.folder, "tiles").put(row)

    def cands(self, folder: Path, p: Path) -> list[Cand] | None:
        sv = self.store(folder, "survey").get(p.name)
        if not sv:
            return None
        tl = []
        if self.wants_tiles(sv):
            for i in range(4):
                t = self.store(folder, "tiles").get(f"{p.name}#{i}")
                if t is None:
                    return None  # wait for every tile, or the candidates would change later
                tl.append(t)
        return candidates(sv, tl)

    # 3. zoom
    def zoom(self):
        jobs = []
        for folder, p in self.photos:
            cs = self.cands(folder, p)
            if not cs:
                continue
            zs = self.store(folder, "zoom")
            todo = [c for c in cs if not zs.get(f"{p.name}@{c.key}")]
            for k in range(0, len(todo), self.st.zoom_per_call):
                part = todo[k:k + self.st.zoom_per_call]

                def build(p=p, part=part):
                    img, content = open_photo(p), []
                    for i, c in enumerate(part, 1):
                        ctx, tight = zoom_images(img, c.box)
                        content += [{"type": "text", "text": f"Bib {i} (a):"}, image_block(ctx),
                                    {"type": "text", "text": f"Bib {i} (b):"}, image_block(tight)]
                    content.append({"type": "text", "text": ZOOM.format(n=len(part))})
                    return params(self.st, self.st.model, content, ZOOM_SCHEMA, 6000, self.st.think)

                jobs.append(Job(f"{folder.name}/{p.name}@{k}", folder, build,
                                dict(photo=p, cands=[c.key for c in part]), self.st.model))
        self.runner.run("zoom", jobs, self._save_zoom)

    def _save_zoom(self, job, data, err, usage):
        m = job.meta
        got = {}
        if data is not None:
            for b in data.get("bibs") or []:
                try:
                    got[int(b.get("id"))] = b
                except (TypeError, ValueError):
                    pass
        for i, ck in enumerate(m["cands"], 1):
            b = got.get(i)
            row = dict(key=f"{m['photo'].name}@{ck}", error=err or (None if b else "no reading for this bib"))
            if b:
                row["read"] = to_read("zoom", b).as_dict()
            self.store(job.folder, "zoom").put(row)

    # 4. judge
    def pending_judge(self, folder, p) -> list[Cand]:
        out = []
        for c in self.cands(folder, p) or []:
            z = self.store(folder, "zoom").get(f"{p.name}@{c.key}")
            if z is not None and decide(c, Read(**z["read"]), None)["status"] == "judge":
                out.append(c)
        return out

    def judge(self):
        jobs = []
        for folder, p in self.photos:
            for c in self.pending_judge(folder, p):
                if self.store(folder, "judge").get(f"{p.name}@{c.key}"):
                    continue
                z = Read(**self.store(folder, "zoom").get(f"{p.name}@{c.key}")["read"])
                lines = []
                for r in c.reads + [z]:
                    label = "whole photo" if r.source == "survey" else ("close-up" if r.source == "zoom" else "photo part")
                    lines.append(f'- {label}: "{r.number or "unreadable"}" ({r.legibility}'
                                 + (f", digits may be hidden: {r.cut}" if r.cut != "none" else "") + ")")
                readings = "\n".join(dict.fromkeys(lines))

                def build(p=p, c=c, readings=readings):
                    ctx, tight = zoom_images(open_photo(p), c.box, context=1.4, target=1024)
                    content = [{"type": "text", "text": "(a)"}, image_block(ctx), {"type": "text", "text": "(b)"},
                               image_block(tight), {"type": "text", "text": "(c)"}, image_block(sharpen(tight)),
                               {"type": "text", "text": JUDGE.format(readings=readings)}]
                    return params(self.st, self.st.judge_model, content, JUDGE_SCHEMA, 16000, self.st.judge_think)

                jobs.append(Job(f"{folder.name}/{p.name}@{c.key}", folder, build,
                                dict(photo=p, cand=c.key), self.st.judge_model))
        self.runner.run("judge", jobs, self._save_judge)

    def _save_judge(self, job, data, err, usage):
        m = job.meta
        row = dict(key=f"{m['photo'].name}@{m['cand']}", error=err)
        if data is not None:
            row["read"] = to_read("judge", data).as_dict()
        self.store(job.folder, "judge").put(row)

    # 5. resolve + results
    def results(self, folder: Path) -> dict:
        entries, order = {}, [p.name for p in photos_in(folder)]
        for p in photos_in(folder):
            sv = self.store(folder, "survey").get(p.name)
            cs = self.cands(folder, p)
            if not sv or cs is None:
                continue
            bibs, complete = [], True
            for c in cs:
                z = self.store(folder, "zoom").get(f"{p.name}@{c.key}")
                j = self.store(folder, "judge").get(f"{p.name}@{c.key}")
                if z is None:
                    complete = False
                d = decide(c, Read(**z["read"]) if z else None, Read(**j["read"]) if j else None)
                d.update(box=c.box, reads=[r.as_dict() for r in c.reads]
                         + ([z["read"]] if z else []) + ([j["read"]] if j else []))
                bibs.append(d)
            entries[p.name] = dict(w=sv["w"], h=sv["h"], bibs=bibs, complete=complete)
        resolve_folder(entries, order, self.st)
        return entries


# --------------------------------------------------------------------------- commands


def settings_from(args) -> Settings:
    st = Settings(model=args.model, judge_model=args.judge_model or args.model, tiles=args.tiles,
                  think=args.think, judge_think=args.judge_think, schema=not args.no_schema,
                  burst_window=args.burst_window)
    st.start = load_start_list(args.start_list)
    return st


def select_photos(root: Path, args) -> list[tuple[Path, Path]]:
    out = []
    for f in batches(root):
        if args.folder and f.name not in args.folder:
            continue
        ph = photos_in(f)
        if args.reviewed:
            rev = read_json(f / REVIEW)
            ph = [p for p in ph if p.name in rev]
        out += [(f, p) for p in ph]
    if args.reviewed and args.limit:
        # A fair sample: every folder, spread over the event, same choice every time.
        rnd = random.Random(7)
        by = defaultdict(list)
        for f, p in out:
            by[f].append((f, p))
        for v in by.values():
            rnd.shuffle(v)
        mixed = []
        while any(by.values()):
            for f in list(by):
                if by[f]:
                    mixed.append(by[f].pop())
        out = mixed
    if args.limit:
        out = out[: args.limit]
    return out


def cmd_run(args) -> int:
    root = Path(args.root).resolve()
    st = settings_from(args)
    photos = select_photos(root, args)
    folders = sorted({f for f, _ in photos}, key=lambda f: natural(f.name))
    print(f"{len(photos)} photo(s) in {len(folders)} folder(s); model {st.model}, tiles {st.tiles}, "
          f"thinking {st.think}/{st.judge_think}" + (", Batch API" if args.batch else ""))
    spend = Spend(args.max_usd)
    pipe = Pipeline(root, photos, st, Runner(args, spend))
    for step in ("survey", "tiles", "zoom", "judge"):
        getattr(pipe, step)()
    write_results(root, pipe, folders)
    print(f"spent this run: ${spend.usd:.2f}  ({spend.calls} calls, {spend.inp:,} in / {spend.out:,} out tokens)")
    if photos:
        log = read_json(root / STATE / "spend.json")
        log["usd"] = round(log.get("usd", 0) + spend.usd, 4)
        log["calls"] = log.get("calls", 0) + spend.calls
        write_json(root / STATE / "spend.json", log)
    if args.reviewed:
        print("\nNext:  sonnet_bibs.py eval --root ...  (compares with what people confirmed)")
    return 0


def write_results(root: Path, pipe: Pipeline, folders) -> None:
    tot = Counter()
    for f in folders:
        res = pipe.results(f)
        write_json(f / STATE / "results.json", res)
        tot["photos"] += len(res)
        tot["with"] += sum(1 for e in res.values() if e["numbers"])
        tot["need"] += sum(1 for e in res.values() if e["needs_human"])
        tot["bibs"] += sum(len(e["numbers"]) for e in res.values())
    print(f"results: {tot['photos']} photo(s), {tot['bibs']} bib(s) accepted, "
          f"{tot['with']} photo(s) with bibs, {tot['need']} need a person")


def all_results(root: Path) -> dict[Path, dict]:
    return {f: read_json(f / STATE / "results.json") for f in batches(root) if (f / STATE / "results.json").exists()}


def cmd_eval(args) -> int:
    """Score against what people confirmed in the review app."""
    root = Path(args.root).resolve()
    rows, mistakes = [], []
    for f, res in all_results(root).items():
        rev = read_json(f / REVIEW)
        old = read_json(f / OLD_SUGGESTIONS_BACKUP) or read_json(f / SUGGESTIONS)
        for name, e in res.items():
            if name not in rev or not e.get("complete", True):
                continue
            truth = {norm(n) for n in rev[name].get("numbers", []) if norm(n) and norm(n).isdigit()}
            new = set(e["numbers"])
            todo = {c for b in e["bibs"] if b["status"] == "review" for c in (b.get("candidates") or [])[:1]}
            oldn = set(old.get(name, {}).get("numbers", [])) if old else None
            rows.append(dict(folder=f.name, truth=truth, new=new, assisted=new | todo, old=oldn,
                             flagged=bool(e["needs_human"])))
            if new != truth:
                mistakes.append([f.name, name, " ".join(sorted(truth)), " ".join(sorted(new)),
                                 " ".join(sorted(new - truth)), " ".join(sorted(truth - new)),
                                 " | ".join(f"{b['status']}:{b.get('number') or b.get('pattern') or ','.join(b.get('candidates') or [])}"
                                            f" ({b.get('how') or b.get('why') or ''})" for b in e["bibs"])])
    if not rows:
        print("nothing to score yet: run  sonnet_bibs.py run --reviewed --limit 100  first")
        return 0

    def score(sel, key):
        tp = sum(len(r[key] & r["truth"]) for r in sel)
        fp = sum(len(r[key] - r["truth"]) for r in sel)
        fn = sum(len(r["truth"] - r[key]) for r in sel)
        ex = sum(r[key] == r["truth"] for r in sel)
        return ex / len(sel), tp / max(1, tp + fn), tp / max(1, tp + fp), fp, fn

    groups = [("ALL", rows)] + [(g, [r for r in rows if r["folder"] == g]) for g in sorted({r["folder"] for r in rows})]
    print(f"\nScored on {len(rows)} photo(s) people checked ({sum(len(r['truth']) for r in rows)} bibs).")
    print("exact = photo has exactly the right numbers; recall = share of real bibs found;")
    print("precision = share of published numbers that are right (a wrong one shows a stranger's photo).\n")
    print(f"{'':18}{'':10}{'exact':>8}{'recall':>8}{'precision':>10}{'wrong':>7}{'missed':>8}")
    for g, sel in groups:
        if not sel:
            continue
        for label, key in (("sonnet", "new"), ("+review", "assisted"), ("old", "old")):
            s = [r for r in sel if r[key] is not None]
            if not s:
                continue
            ex, rc, pr, fp, fn = score(s, key)
            print(f"{(g if label == 'sonnet' else ''):18}{label:10}{ex:>8.1%}{rc:>8.1%}{pr:>10.1%}{fp:>7}{fn:>8}")
        print(f"{'':18}{'flagged':10}{sum(r['flagged'] for r in sel) / len(sel):>8.1%}  of photos go to a person")
    out = root / STATE / "eval_mistakes.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["folder", "photo", "people", "sonnet", "sonnet_wrong", "sonnet_missed", "bibs (status:number (how))"])
        w.writerows(mistakes)
    print(f"\n'+review' = if a person accepts the top suggestion on flagged bibs.  "
          f"Differences, photo by photo: {out}")
    print("Note: people's answers were made with the old pipeline's suggestions pre-filled, and some "
          "folders came from a CSV, so a 'mistake' is sometimes the truth being wrong. Check a few.")
    return 0


def cmd_estimate(args) -> int:
    """Cost before spending: token math on the real photo sizes."""
    root = Path(args.root).resolve()
    photos = select_photos(root, args)
    if not photos:
        print("no photos")
        return 0
    st = settings_from(args)
    sample = photos[:: max(1, len(photos) // 200)]
    pin, pout = PRICES.get(st.model, PRICES["claude-sonnet-5-5"])
    jin, jout = PRICES.get(st.judge_model, PRICES["claude-sonnet-5-5"])
    prompt = (len(SYSTEM) + len(SURVEY)) // 3.2
    sv_in = sum(img_tokens(*fit_size(*Image.open(p).size, max_factor=1.0)) for _, p in sample) / len(sample) + prompt
    W, H = Image.open(sample[0][1]).size
    rect = tile_rects(W, H)[0]
    tile_in = img_tokens(*fit_size(rect[2] - rect[0], rect[3] - rect[1], 2.5)) + prompt
    think = {"off": 0, "low": 150, "medium": 500, "high": 1200}
    bibs = args.bibs_per_photo
    sv_out = 60 + 45 * bibs + think[st.think]
    zoom_in = bibs * (2 * 560 + 20) + len(ZOOM) // 3.2 + len(SYSTEM) // 3.2
    zoom_out = 50 + 55 * bibs + think[st.think]
    tile_share = {"off": 0, "auto": args.tile_share, "always": 1.0}[st.tiles]
    tl_in, tl_out = 4 * tile_in * tile_share, 4 * (60 + 30 * bibs + think[st.think]) * tile_share
    j_share = args.judge_share * bibs
    j_in, j_out = j_share * (3 * 900 + 900), j_share * (120 + think[st.judge_think] * 2)
    usd = ((sv_in + tl_in + zoom_in) * pin + (sv_out + tl_out + zoom_out) * pout + j_in * jin + j_out * jout) / 1e6
    n = len(photos)
    print(f"{n} photo(s), ~{bibs} bibs each, tiles {st.tiles} (~{tile_share:.0%} of photos), "
          f"judge on ~{args.judge_share:.0%} of bibs, thinking {st.think}/{st.judge_think}")
    print(f"  per photo: survey {sv_in:,.0f}+{sv_out:,.0f}  tiles {tl_in:,.0f}+{tl_out:,.0f}  "
          f"zoom {zoom_in:,.0f}+{zoom_out:,.0f}  judge {j_in:,.0f}+{j_out:,.0f}  tokens (in+out)")
    print(f"  ${usd:.4f} per photo  ->  live ${usd * n:,.0f}   Batch API ${usd * n / 2:,.0f}"
          f"   (per 1,000 photos: ${usd * 1000:.0f} / ${usd * 500:.0f})")
    print("  An estimate: run  run --reviewed --limit 100  and the real cost per photo is printed.")
    return 0


def cmd_status(args) -> int:
    root = Path(args.root).resolve()
    st = settings_from(args)
    print(f"{'folder':24}{'photos':>8}{'survey':>8}{'tiles':>7}{'zoom':>7}{'judge':>7}{'done':>7}{'need you':>10}")
    for f in batches(root):
        ph = photos_in(f)
        pipe = Pipeline(root, [(f, p) for p in ph], st, None)
        sv = sum(1 for p in ph if pipe.store(f, "survey").get(p.name))
        res = read_json(f / STATE / "results.json")
        rev = read_json(f / REVIEW)
        need = sum(1 for n, e in res.items() if e["needs_human"] and n not in rev)
        print(f"{f.name[:24]:24}{len(ph):>8}{sv:>8}{len(pipe.store(f, 'tiles').rows):>7}"
              f"{len(pipe.store(f, 'zoom').rows):>7}{len(pipe.store(f, 'judge').rows):>7}{len(res):>7}{need:>10}")
    log = read_json(root / STATE / "spend.json")
    if log:
        print(f"spent so far: ${log.get('usd', 0):.2f} in {log.get('calls', 0)} calls")
    return 0


def review_entry(e: dict) -> dict:
    """review_desktop.py format: green boxes for accepted bibs, orange for 'look here'."""
    persons = []
    for b in e["bibs"]:
        if b["status"] == "drop":
            continue
        if b["status"] == "accept":
            persons.append(dict(box=b["box"], ocr=[[b["number"], 0.99]], unsure=False, verdict="agree",
                                needs_human=False, haiku=dict(numbers=[b["number"]])))
        else:
            cands = b.get("candidates") or ([b["pattern"]] if b.get("pattern") else [])
            cands = [c for c in cands if "?" not in c]
            persons.append(dict(box=b["box"], ocr=[[c, 0.5] for c in cands], unsure=True, verdict="disagree",
                                needs_human=True, haiku=dict(numbers=cands[:1]), note=b.get("why", ""),
                                pattern=b.get("pattern", "")))
    return dict(numbers=e["numbers"], needs_human=e["needs_human"], persons=persons, source="sonnet",
                w=e.get("w"), h=e.get("h"))


def cmd_review(args) -> int:
    """Put Sonnet's results into the review app (the raceday suggestions are kept aside)."""
    root = Path(args.root).resolve()
    for f, res in all_results(root).items():
        sug, bak = f / SUGGESTIONS, f / OLD_SUGGESTIONS_BACKUP
        if args.undo:
            if bak.exists():
                bak.replace(sug)
                print(f"{f.name}: raceday suggestions restored")
            continue
        if sug.exists() and not bak.exists():
            sug.replace(bak)
        old = read_json(bak)
        out = {}
        for p in photos_in(f):
            if p.name in res:
                out[p.name] = review_entry(res[p.name])
            elif p.name in old:
                out[p.name] = old[p.name]  # not processed by Sonnet yet: keep the old suggestion
        write_json(sug, out)
        need = sum(1 for n, e in res.items() if e["needs_human"] and n not in read_json(f / REVIEW))
        print(f"{f.name}: {len(res)} photo(s) from Sonnet in the review app, {need} need you "
              f"(old suggestions kept in {OLD_SUGGESTIONS_BACKUP})")
    if args.undo:
        return 0
    print("Open:  python review_desktop.py <root>    ('sonnet_bibs.py review --undo' puts the old ones back)")
    print("Careful: raceday.py scan/check/recheck rewrite the review app's file; run  review  again afterwards.")
    return 0


def cmd_export(args) -> int:
    """bib_export.csv + review_all.json, same format as raceday.py, for web/scripts/import-bibs.mjs.
    What people confirmed in the review app always wins over Sonnet."""
    root = Path(args.root).resolve()
    rows, review_all, s = [], {}, Counter()
    for f, res in all_results(root).items():
        rev = read_json(f / REVIEW)
        for p in photos_in(f):
            key = p.relative_to(root).as_posix()
            if p.name in rev:
                nums, s["reviewed"] = rev[p.name].get("numbers", []), s["reviewed"] + 1
            elif p.name in res:
                nums, s["sonnet"] = res[p.name]["numbers"], s["sonnet"] + 1
            else:
                s["missing"] += 1
                continue
            rows.append([key, ", ".join(nums)])
            review_all[key] = {"numbers": nums, "model_numbers": nums}
    out = root / "_publish_sonnet"
    out.mkdir(exist_ok=True)
    with (out / "bib_export.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["image_name", "bib_numbers"])
        w.writerows(rows)
    write_json(out / "review_all.json", review_all)
    print(f"{len(rows)} photo(s): {s['reviewed']} as people confirmed, {s['sonnet']} from Sonnet"
          + (f"; {s['missing']} not processed yet (left out)" if s["missing"] else "") + f"\n-> {out}")
    print("Publish tags (from MarathonOCR/web):  node scripts/import-bibs.mjs --csv "
          f"\"{out / 'bib_export.csv'}\" --review \"{out / 'review_all.json'}\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "estimate", "eval", "status", "review", "export"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", required=True, help="folder that holds the photographer folders")
        sp.add_argument("--folder", nargs="*", help="only these photographer folders (names)")
        sp.add_argument("--reviewed", action="store_true", help="only photos people already checked (for a trial)")
        sp.add_argument("--limit", type=int, help="only the first N photos")
        sp.add_argument("--start-list", help="txt (one bib per line) or csv with a 'bib' column")
        sp.add_argument("--model", default=MODEL)
        sp.add_argument("--judge-model", help="model for disagreements (default: same as --model)")
        sp.add_argument("--tiles", choices=["off", "auto", "always"], default="auto",
                        help="enlarged quarters: auto = crowded or doubtful photos only")
        sp.add_argument("--think", choices=["off", "low", "medium", "high"], default="medium")
        sp.add_argument("--judge-think", choices=["off", "low", "medium", "high"], default="high")
        sp.add_argument("--no-schema", action="store_true", help="ask for JSON in the prompt instead of structured outputs")
        sp.add_argument("--burst-window", type=int, default=6, help="neighbouring frames each side for bursts")
        if name == "run":
            sp.add_argument("--batch", action="store_true", help="Batch API: half price, slower; re-run to collect")
            sp.add_argument("--workers", type=int, default=8, help="parallel requests (live mode)")
            sp.add_argument("--max-usd", type=float, help="stop when this run has spent this much")
        if name == "estimate":
            sp.add_argument("--bibs-per-photo", type=float, default=3.0)
            sp.add_argument("--tile-share", type=float, default=0.55, help="share of photos that get tiles (auto)")
            sp.add_argument("--judge-share", type=float, default=0.15, help="share of bibs that go to the judge")
        if name == "review":
            sp.add_argument("--undo", action="store_true", help="put the raceday suggestions back")
    args = ap.parse_args()
    return {"run": cmd_run, "estimate": cmd_estimate, "eval": cmd_eval, "status": cmd_status,
            "review": cmd_review, "export": cmd_export}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
