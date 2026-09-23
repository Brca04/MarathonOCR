#!/usr/bin/env python3
"""Read bib numbers from the test gallery on this Mac's GPU (Apple MPS).

Same method as the cloud run: YOLO finds people, EasyOCR reads digits in each
person crop. Picks up where _transfer/ocr_all.jsonl left off, so it only does
the photos that are still missing.

    cd ~/Projects/MarathonOCR
    python3 -m venv .venv-mac && source .venv-mac/bin/activate
    pip install torch torchvision easyocr ultralytics pillow
    python scripts/ocr_gallery_mac.py
"""
import json, os, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
from marathon_ocr.recognizers.base import Reading  # noqa: E402

import torch, easyocr  # noqa: E402
from ultralytics import YOLO  # noqa: E402

DEV = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
SRC = ROOT / 'src' / 'slike'
OUT = ROOT / '_transfer' / 'ocr_all.jsonl'
CAP = 1400

done = {json.loads(l)['file'] for l in OUT.open()} if OUT.exists() else set()
files = sorted(SRC.glob('*.jpg'), key=lambda p: int(p.stem.split(' - ')[1]))
todo = [(p, f"{int(p.stem.split(' - ')[1]):04d}.jpg") for p in files]
todo = [t for t in todo if t[1] not in done]
print(f'device={DEV}  done={len(done)}  todo={len(todo)}', flush=True)

yolo = YOLO('yolo11n.pt')
reader = easyocr.Reader(['en'], gpu=DEV != 'cpu', verbose=False)

with OUT.open('a') as fh:
    for i, (path, name) in enumerate(todo, 1):
        t0 = time.time()
        im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
        if max(im.size) > 2000:
            im.thumbnail((2000, 2000), Image.LANCZOS)
        hits, people = [], []
        for r in yolo.predict(im, classes=[0], conf=0.3, device=DEV, verbose=False):
            for b in r.boxes:
                people.append(([float(v) for v in b.xyxy[0]], float(b.conf[0])))
        for (x0, y0, x1, y1), pc in people:
            h = y1 - y0
            if h < 80:
                continue
            cy0, cy1 = y0 + 0.12 * h, y0 + 0.92 * h
            crop = im.crop((round(x0), round(cy0), round(x1), round(cy1)))
            s = 1.0
            if crop.height > CAP:
                s = CAP / crop.height
                crop = crop.resize((max(1, round(crop.width * s)), CAP), Image.LANCZOS)
            for box, text, conf in reader.readtext(np.array(crop), allowlist='0123456789', detail=1, paragraph=False):
                for tx, c in Reading.from_raw([(text, float(conf))]).candidates:
                    xs = [p[0] for p in box]; ys = [p[1] for p in box]
                    hits.append(dict(text=tx, conf=round(c, 4),
                                     bbox=[round(x0 + min(xs) / s), round(cy0 + min(ys) / s),
                                           round(x0 + max(xs) / s), round(cy0 + max(ys) / s)],
                                     h=round((max(ys) - min(ys)) / s), pconf=round(pc, 3)))
        fh.write(json.dumps(dict(file=name, w=im.width, h=im.height, regions=len(people),
                                 hits=hits, secs=round(time.time() - t0, 2))) + '\n')
        fh.flush()
        if i % 20 == 0 or i == len(todo):
            print(f'{i}/{len(todo)}', flush=True)
print('DONE', flush=True)
