# MarathonOCR

Bib-number recognition for a race photo gallery: runners type their number, find their photos.

This repo is currently **Milestone 1 — the evaluation harness**. Everything else in the plan depends on being able to measure a pipeline, so that is built first.

---

## The dataset

`archive/` holds 30 photos with 146 hand-drawn bib boxes in CVAT 1.1 format. It is an **evaluation set, not a training set** — far too small to train a detector, exactly the right size to score one.

```
images        30
boxes        146   all legible
rotated      100   (68% — runners lean, bibs crumple)
box height   p10 11px | median 19px | p90 42px
             82 boxes under 20px, 118 under 32px
```

**That median of 19px is the most important number in the project.** No OCR engine reads a 19px-tall number out of a full frame, which rules out the naive "run OCR on the photo" design and forces a three-stage pipeline:

```
detect person  →  crop torso  →  deskew + upscale  →  recognize digits
```

Note that these samples are downscaled web images (some only 900×600). A photographer's originals are ~6000px wide, where the same bib is 120–150px and comfortably readable. Treat this set as a deliberately pessimistic benchmark: what works here will be excellent on real files.

## Baseline results

EasyOCR with a digit allowlist, on ground-truth crops (detection error removed — this is the **upper bound** for any pipeline using this recognizer):

| bucket | n | exact | fuzzy@1 | CER | blank |
|---|---:|---:|---:|---:|---:|
| all | 146 | 78.8% | **91.1%** | 0.090 | 2.1% |
| tiny (<20px) | 82 | 76.8% | 89.0% | 0.105 | 2.4% |
| small (20–40px) | 47 | 80.9% | 91.5% | 0.079 | 2.1% |
| large (≥40px) | 17 | 82.4% | **100.0%** | 0.046 | 0.0% |

Three things this tells us:

1. **Fuzzy search is worth more than a better model.** Going from exact to edit-distance-1 adds **+12.3 points** for free. Postgres `pg_trgm` in front of the recognizer buys more accuracy than weeks of model tuning would.
2. **Every box ≥40px is recoverable.** 100% fuzzy@1. Source resolution matters more than the recognizer — push photographers for originals, never resized JPEGs.
3. **Failures are mostly truncation, not hallucination.** `1514 → 14`, `3885 → 88`, `849 → 09`. The engine is dropping leading digits on blurred crops rather than inventing numbers. That is the failure mode you want, and it is what makes prefix/suffix-tolerant matching effective.

Reproduce with `python scripts/eval_recognizers.py --engines easyocr`.

On an RTX 5070 this runs at **10.4 ms/crop** (vs 111 ms on CPU). A 20k-photo event is roughly 60k crops — about 10 minutes of recognition. The local-GPU-as-backend design holds.

## Confidence calibration → the cascade

The more useful measurement. EasyOCR's confidence predicts its own correctness almost perfectly on this data:

| confidence | n | share | exact | fuzzy@1 |
|---|---:|---:|---:|---:|
| 0.8–1.0 | 98 | 67% | 90.8% | **100.0%** |
| 0.6–0.8 | 23 | 16% | 73.9% | 95.7% |
| 0.4–0.6 | 11 | 8% | 72.7% | 90.9% |
| 0.2–0.4 | 8 | 5% | 12.5% | 37.5% |
| 0.0–0.2 | 6 | 4% | 0.0% | 0.0% |

Every read above 0.8 was correct within edit distance 1, and essentially all errors sit in the bottom ~9%. So the question is not "which recognizer is best" but **"how little work can the expensive one do"**:

| threshold | accepted | exact | fuzzy@1 | deferred |
|---|---:|---:|---:|---:|
| 0.3 | 92.5% | 85.2% | 97.0% | 11 |
| **0.4** | **90.4%** | **86.4%** | **98.5%** | **14** |
| 0.6 | 82.9% | 87.6% | 99.2% | 25 |
| 0.7 | 78.1% | 89.5% | 100.0% | 32 |

`CascadeRecognizer` implements this: EasyOCR runs on everything, and only sub-threshold crops escalate to a VLM. At 0.4 that is ~6k fallback calls per 20k-photo event — a few dollars per race, against ~$60 to run a VLM over everything or 91% accuracy with no fallback.

```python
from marathon_ocr.recognizers import build_cascade
recognizer = build_cascade(primary="easyocr", fallback="vlm", threshold=0.4)
```

Calibration is a property of the *whole* pipeline — engine, padding, upscale target — not a constant. Re-run `scripts/calibrate.py` after changing any of them.

## End-to-end: where the accuracy actually goes

Everything above measures recognition on perfect human-drawn crops. `scripts/eval_end_to_end.py` measures the real thing — detector finds the bibs, recognizer reads them — and reports **photo recall**: for each (photo, bib) a human annotated, did the pipeline surface that number anywhere in that photo? That is literally "will the runner find their photo".

Provisional, on the first 10 photos / 23 bibs (CPU; rerun on GPU for the full set):

| stage | fuzzy@1 |
|---|---:|
| recognition on ground-truth crops | 91.1% |
| end-to-end, torso-heuristic detector | **73.9%** |

**Detection is costing ~17 points**, and precision is only 48.6% — roughly half the numbers surfaced are spurious, at 7.2 predictions per photo. That is the whole case for the detector work: recognition is close to solved, detection is not.

Precision matters as much as recall here. A missed bib means a runner doesn't see one of their photos; a false positive puts a stranger's photo into their results, which is the worse failure.

```bash
python scripts/eval_end_to_end.py --detector whole --detector torso
```

The `whole` control hands the entire frame to the recognizer. Run it once to see what person-cropping buys — at a 19px median bib height in a full frame, it should fail badly, and having that measured is what justifies the two-stage design.

### A note on PaddleOCR

Skip it on this setup. `paddlepaddle-gpu` builds lag CUDA releases badly and Blackwell + Windows is the worst case; you can lose a day to it. Given EasyOCR already reaches 98.5% fuzzy@1 under the cascade, the remaining gains are in *detection* and in the fallback tier, not in swapping classical OCR engines.

## Layout

```
src/marathon_ocr/
  dataset.py          CVAT parser. Handles rotation correctly — 68% of boxes
                      are rotated, and ignoring that silently corrupts crops.
  crops.py            Deskew, pad, upscale. Same code path in benchmark and
                      production, deliberately.
  metrics.py          exact / CER / fuzzy@1, sliced by crop height.
  pipeline.py         detect -> crop -> upscale -> recognize, over a photo.
  recognizers/        Pluggable engines behind one interface.
    base.py           Reading = ranked candidate list, never one string.
    engines.py        easyocr, paddleocr, trocr, vlm
    cascade.py        Fast primary + fallback on low confidence.
  detectors/          Person detection (stock YOLO) + bib detection (yours).
scripts/
  check_env.py        Verify the GPU stack. Run this first.
  extract_crops.py    Export ground-truth crops + labels.csv.
  eval_recognizers.py Score engines against the eval set.
  calibrate.py        Confidence-vs-accuracy table; picks the cascade threshold.
  eval_end_to_end.py  Full-frame pipeline; reports photo recall + precision.
benchmark/            Generated. Crops, labels, per-engine JSON results.
```

## Setup

The RTX 5070 is Blackwell, compute capability **sm_120**. Stock PyTorch wheels are not built for it and fail at the first kernel launch with `no kernel image is available for execution on the device` — which reads like a driver problem and is not. Install the cu128 build first:

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
python scripts/check_env.py     # must confirm sm_120 and a successful GPU matmul
```

`check_env.py` runs a real matmul rather than just checking `is_available()`, because capability checks pass on builds that still cannot execute.

```bash
python scripts/extract_crops.py
python scripts/eval_recognizers.py --engines easyocr paddleocr
```

## Design decisions worth knowing

**Recognizers return ranked candidates, not a string.** `Reading` carries a list. Collapsing to one answer throws away exactly the information the fuzzy search layer needs downstream.

**Normalisation is shared.** `normalise_digits()` maps OCR confusions (`O→0`, `l→1`, `S→5`) and enforces a 2–6 digit length. It runs identically in the harness and in production — normalisation that exists only in the benchmark is how a benchmark starts lying to you.

**Detection is split in two.** `PersonDetector` uses stock COCO weights and needs no training data, turning "find a 19px object in a 6000px frame" into "find it in a 400px crop". `YOLOBibDetector` is the part you fine-tune. `TorsoHeuristicDetector` is a crude stand-in so the end-to-end pipeline runs today.

**The metric is fuzzy@1, not exact.** The product question is "did the runner find their photo?", and with trigram search in front, edit-distance-1 is the honest proxy.

## Where this is going

Target architecture — your 5070 is the backend, so there is no cloud GPU cost:

```
photos on disk → local GPU batch job → R2 (originals) + Supabase (detections)
                                              ↓
                              Cloudflare Worker + Astro (read-only site)
                                              ↓
                          runner types "1308" → pg_trgm fuzzy match → photos
```

Ingest is an offline batch you run per event, not a live service. That removes queues, autoscaling and cold starts from the prototype entirely.

**Next steps**

Recognition is effectively solved for the prototype (98.5% fuzzy@1 under the cascade). Detection is the open problem — it is currently a torso heuristic.

1. Detector training data: [public RBNR sets](https://github.com/Lwhieldon/BibObjectDetection) + synthetic bib composites; fine-tune single-class YOLO11s.
2. End-to-end eval: detection recall × recognition accuracy on full frames. This is the number that predicts the product.
3. Wire the VLM fallback and confirm the cascade economics on real deferrals.
4. Local ingest CLI → R2 + Supabase.
5. Astro site on Cloudflare Workers: event page, search box, results grid.

Schema sketch:

```sql
create extension if not exists pg_trgm;

events     (id, slug, name, date)
photos     (id, event_id, r2_key, captured_at, width, height)
detections (id, photo_id, bbox, text, confidence, rank)

create index on detections using gin (text gin_trgm_ops);
```

Store *every* candidate per bib. Rank matches by `confidence × similarity`.
