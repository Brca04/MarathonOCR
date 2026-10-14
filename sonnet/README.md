# Sonnet bib reader

A separate, accuracy-first pipeline: Claude Sonnet 5.5 only (no YOLO, no EasyOCR).
It reads the same photographer folders as `raceday.py` and writes only into a hidden
`.sonnet` folder inside each one, so the old pipeline keeps working untouched.

## How it reads a photo

| Step | What Sonnet sees | Why |
|---|---|---|
| 1. survey | the whole photo at full resolution (2000×1333 is sent unshrunk) | finds every bib, with a box, including unreadable ones |
| 2. tiles | 4 overlapping quarters, enlarged about 2× (crowded or doubtful photos only) | small background bibs |
| 3. zoom | every bib cut from the original, enlarged: runner and outlined bib, plus a close-up | an independent second reading of each bib |
| 4. judge | only bibs whose readings disagree: 3 fresh crops and the earlier readings, with extra thinking | settles disagreements |
| 5. resolve | free, no API calls: neighbouring frames and the start list | "23?5" next to frames with a clear 2315 becomes 2315 |

A number is published only when independent readings agree or the judge is certain.
Everything else goes to the review app with the candidates pre-filled.

## Commands (from the MarathonOCR folder, with the .venv active)

```bat
:: 1. Cost first, no API calls
python sonnet\sonnet_bibs.py estimate --root C:\Users\bruno\Desktop\marathonZG

:: 2. Trial on 100 photos that people already checked (about $8), then score it
python sonnet\sonnet_bibs.py run  --root C:\Users\bruno\Desktop\marathonZG --reviewed --limit 100 --max-usd 15
python sonnet\sonnet_bibs.py eval --root C:\Users\bruno\Desktop\marathonZG

:: 3. Everything, half price through the Batch API (you can close the window and re-run later to collect results)
python sonnet\sonnet_bibs.py run --root C:\Users\bruno\Desktop\marathonZG --batch

:: 4. Review in the usual app, then export for the site
python sonnet\sonnet_bibs.py review --root C:\Users\bruno\Desktop\marathonZG
python review_desktop.py C:\Users\bruno\Desktop\marathonZG
python sonnet\sonnet_bibs.py export --root C:\Users\bruno\Desktop\marathonZG

python sonnet\sonnet_bibs.py status --root C:\Users\bruno\Desktop\marathonZG
```

Useful options: `--start-list bibs.csv` (strongly recommended), `--folder "Omar Mocic"`,
`--tiles off|auto|always`, `--think off|low|medium|high`, `--judge-model claude-opus-5-5`.

If the API rejects structured outputs or the thinking settings, add `--no-schema` or `--think off`.

`eval` compares the results with `.marathon_ocr_review.json` (what people confirmed) and with the
old pipeline's numbers on the same photos. It also writes `.sonnet/eval_mistakes.csv`, one row per
photo that differs.

## Cost (Sonnet 5.5: $2 / $10 per million tokens in / out; Batch API half price)

Estimated from the real photo size (2000×1333 = 3,456 image tokens) and about 3 bibs per photo.
`run` prints the real spend, so the 100-photo trial confirms these figures.

| Setting | per photo | Zagreb, 9,844 photos (live / batch) | 20k-photo event (batch) |
|---|---:|---:|---:|
| max: `--tiles always` | $0.116 | $1,140 / $570 | $1,160 |
| **default: tiles auto, thinking medium** | **$0.084** | **$830 / $415** | **$840** |
| balanced: `--think low --judge-think medium` | $0.063 | $620 / $310 | $630 |
| lean: `--tiles off --think off --judge-think medium` | $0.029 | $290 / $145 | $290 |

Tests (no API key needed): `python sonnet\test_sonnet_bibs.py`
