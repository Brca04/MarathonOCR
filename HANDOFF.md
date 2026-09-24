# MarathonOCR: handoff

_Last updated 25 Sep 2026. Paste this file into a new chat to resume._

## What this is
MarathonOCR reads race-bib numbers in photos and powers a site where runners search for their photos.
Owner: Bruno Cavor. Git branch: `zeljava-demo`, latest commit `34d67d0`. **Run `git push` from the Mac if it hasn't been pushed yet.**

- **Live demo:** https://marathonocr.bruno-cavor.workers.dev (Željava Half Marathon 2026, 663 photos, real results)
- **Site:** Next.js 16 static export on Cloudflare Workers, with the guard Worker in `web/worker/index.ts`. Data is in Supabase, project `gqjahxadfodnmbpetgyh`.
- **Publishing:** `npm run export:static`, then `npm run deploy` (from `web/`, with values from `web/.env.demo`).

## The key finding: where to resume
The Željava recognition run **did not use the trained bib detector.** `models/bib_detector/best.pt` exists only on the Windows RTX 5070 PC. On the Mac, `scripts/ocr_gallery_mac.py` and `scripts/haiku_check.py` used stock `yolo11n.pt`, which detects people rather than bibs. They cropped each runner's torso and ran EasyOCR on it.

Scored against the hand-made answer key (514 photo–bib pairs), **that stand-in** got:

| Result | Share |
|---|---|
| Found | 66% |
| Seen but misread or low confidence | 11% |
| Never seen (the detection problem) | 23% |

This scores the stand-in, not the real system. **The trained model has never been measured on Željava.**

## Next steps, on the 5070 PC
1. Run `git fetch` and `git checkout zeljava-demo`. Copy the Željava photos (`src/slike/`, 2.2 GB, not in git) over from the Mac.
2. Confirm `models/bib_detector/best.pt` exists.
3. Run the real pipeline (`scripts/run.py` / `make_demo_gallery.py`, which use `best.pt`) on `src/slike` at full resolution, without the 2000 px downscale.
4. Score the output against `data/answer_keys/zeljava-2026.json` with the same found / misread / never-seen breakdown, plus precision with the start-list filter.
5. Decide the next step based on that score, **no Claude API spend until then.**

## Constraints the user set
- Budget: **no Claude call per image.** Events have 20k–40k photos and the API budget is small.
- Accuracy of core recognition comes first. Faster manual review comes later; the user is fine reviewing.
- Earlier the user said "just propose" for the recognition redesign: propose first, then build once agreed.

## Proposed plan, after the baseline number
1. **Detector:** full resolution with tiling. Consider an Apache-licensed model (RF-DETR or YOLOX) to avoid Ultralytics' AGPL licence; the Enterprise licence price isn't public. Boxes can be auto-labelled from the answer key.
2. **Reader:** fine-tune PARSeq (Apache) on bib crops plus synthetic bibs. Only allow start-list numbers (310 bibs, range 1–400); on the old data this cut wrong reads 140 → 92.
3. **Bursts:** carry a confirmed bib to neighbouring frames (same camera, EXIF time seconds apart), flagged for review.
4. **Claude only on small crops of the leftover uncertain cases**, through the Batch API with a cap per event: about $5–15 per 20k photos, versus about $240 to send every full photo.
5. **Later:** faster review (group bursts, show crop strips, keyboard shortcuts).

## Important files
- `data/answer_keys/zeljava-2026.{csv,json}`: 663 human-reviewed photos, the scoring truth.
- `review_app.py` (Streamlit): Add buttons per read, autosave, macOS folder picker. Run with `-- --folder src/slike`.
- `scripts/haiku_check.py` and `src/marathon_ocr/verify.py`: Haiku second opinion (crops plus an optional whole-photo pass).
- `scripts/make_suggestions.py`: turns OCR output into pre-filled review suggestions.
- `web/`: the site. See `web/README.md` sections "Race-day traffic" and "Bot and scraper protection".

## Open items
- **Security:** the Cloudflare API token pasted in the earlier chat must be deleted or rolled in the Cloudflare dashboard. The Anthropic key goes only in `.env`, never committed.
- Media on R2 for large events (Workers allows 20k asset files); a one-command publish; Turnstile keys (`NEXT_PUBLIC_TURNSTILE_SITEKEY`, `TURNSTILE_SECRET`); a custom domain; legal documents and photographer permission; the YOLO licence decision; a distributed load test.
