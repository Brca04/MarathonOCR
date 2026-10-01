# MarathonOCR: System Design and Architecture

| | |
|---|---|
| **Document owner** | Bruno Cavor |
| **Status** | Living document. Reflects the system as of 1 October 2026, branch `zeljava-demo` @ `dfd231f` |
| **Audience** | Engineers joining the project, technical partners, and anyone evaluating the system for an event |
| **Reference deployment** | Željava Air Base Half Marathon 2026: https://marathonocr.bruno-cavor.workers.dev |

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Problem statement](#2-problem-statement)
3. [Scope](#3-scope)
4. [Actors and use cases](#4-actors-and-use-cases)
5. [System context](#5-system-context)
6. [Architecture overview](#6-architecture-overview)
7. [Component design](#7-component-design)
8. [Data model](#8-data-model)
9. [Search and matching semantics](#9-search-and-matching-semantics)
10. [Event lifecycle: end-to-end flow](#10-event-lifecycle-end-to-end-flow)
11. [Security, abuse protection and privacy](#11-security-abuse-protection-and-privacy)
12. [Performance, scalability and capacity](#12-performance-scalability-and-capacity)
13. [Recognition quality: what has been measured](#13-recognition-quality-what-has-been-measured)
14. [Cost model](#14-cost-model)
15. [Deployment and operations](#15-deployment-and-operations)
16. [Configuration reference](#16-configuration-reference)
17. [Repository layout](#17-repository-layout)
18. [Architecture decision records](#18-architecture-decision-records)
19. [Known limitations and risks](#19-known-limitations-and-risks)
20. [Roadmap](#20-roadmap)
21. [Glossary](#21-glossary)

---

## 1. Executive summary

MarathonOCR turns a race photographer's raw photo dump into a searchable gallery: a runner types their bib number and gets every photo they appear in, together with their official result.

The system has two halves with very different requirements:

| Half | What it does | Runs where | Character |
|---|---|---|---|
| **Ingest** | Finds and reads bib numbers in 10k–40k photos; a human confirms the uncertain ones | Organizer's or operator's local GPU machine (RTX 5070 or Apple Silicon) | Offline batch, once per event, accuracy-critical, cost-sensitive |
| **Serve** | Lets runners search and download their photos | Cloudflare edge (Workers + static assets + R2), Supabase Postgres as source of truth | Online, read-only, spiky traffic (up to 10k concurrent users after a race), abuse-exposed |

The central design choice is that **the two halves never run at the same time**. Recognition and review finish first; the result is *published* as a static snapshot (one small JSON file per bib) that the edge serves without touching the database. That one choice removes queues, autoscaling, cold starts and database capacity planning from race day.

**Current maturity.** The serving half is production-shaped: deployed, auto-deploying from GitHub, bot-protected with Turnstile, serving a real event with real results. The ingest half works end to end with a human in the loop, but **automatic recognition accuracy is the main open problem** (see §13). The trained bib detector has not yet been measured on the reference event.

---

## 2. Problem statement

At a mid-sized race, a few photographers produce 10,000–40,000 photos. Runners want *their* photos, ideally within hours of finishing. Today that means scrolling through thousands of thumbnails, or the organizer paying a commercial service.

Technically, finding a runner in a photo means **reading a race bib**. That is harder than it looks:

- **Bibs are tiny in the frame.** In the original evaluation set the median bib is **19 px tall**. No general OCR engine reads that from a full frame.
- **Bibs are distorted.** 68% of annotated bibs are rotated. Bibs crumple, are partly covered by arms, safety pins, jackets and other runners, and are motion-blurred.
- **There is a lot of distracting text.** Sponsor logos, timing clocks, shirt prints and signage all contain digits.
- **The two failure modes are not equal.** A *missed* photo is a mild disappointment. A *stranger's* photo in your gallery is a privacy problem and destroys trust. The system is deliberately tuned to prefer precision over recall when the two conflict.
- **Budget.** Sending every photo to a frontier vision model would work reasonably well, but costs roughly $240 per 20k photos. That is above what a small organizer will pay.

---

## 3. Scope

### 3.1 In scope

| Area | Capability |
|---|---|
| Recognition | Bib detection and digit recognition on local GPU; confidence calibration; optional LLM second opinion on uncertain reads |
| Human review | Desktop review app: confirm, add or remove bibs per photo, keyboard-light workflow, autosave, CSV export |
| Results | Import of official results (name, club, category, times, placings) from timing-company CSV exports, Croatian and English column names |
| Publishing | Static per-bib export, photo derivatives (web and thumbnail), upload to R2, automatic deploy |
| Runner site | Bilingual (HR/EN) landing page, bib search, runner page with result and photo grid, lightbox, single and bulk download, privacy and contact pages |
| Protection | Signed sessions, Turnstile bot check, unguessable photo URLs, database locked to the edge |
| Per-event branding | Name, colours, logo, hero image, race labels, all from environment variables |

### 3.2 Explicitly out of scope (removed or deferred)

| Item | Status |
|---|---|
| Payments / paid downloads | **Removed** at the owner's request; tables dropped |
| Course map / GPS track | **Removed** |
| Face recognition | **Not planned.** Legally sensitive (biometric data under GDPR Art. 9) and unnecessary when bibs work |
| Live, during-race ingestion | Not planned for v1; ingest is an offline batch |
| Multi-event portal on one deployment | Deferred; one deployment serves one event (see §19) |
| Runner accounts / logins | Not planned; search is anonymous |
| Photographer self-service upload | Deferred; the operator loads photos |

---

## 4. Actors and use cases

### 4.1 Actors

| Actor | Goal | Touches |
|---|---|---|
| **Runner** | Find and download their photos; see their result | Public website only |
| **Organizer** | Offer a photo service with minimal effort and cost; protect runners' privacy | Supplies results CSV, photos and branding; approves publication |
| **Photographer** | Photos used with credit; originals not leaked | Supplies photos; credited on the site |
| **Operator** (currently Bruno) | Run ingest, review and publish per event | Local GPU machine, review app, CLI scripts, Cloudflare and Supabase dashboards |
| **Scraper / bot** (adversary) | Bulk-download galleries or harvest names | Public endpoints |

### 4.2 Use cases

**UC-1: Runner finds their photos (primary)**

1. The runner opens the event site (typically on a phone, often on race-venue Wi-Fi shared by hundreds).
2. They enter their bib number and accept the privacy notice.
3. The browser gets a session, silently passing Turnstile.
4. The runner page shows:
   - name, race and distance, official time, pace, overall and category place, club;
   - a hero photo where they are the subject;
   - a grid of every photo matched to their bib.
5. They open photos in a lightbox, download one, or download all.

*Postconditions:* no database call on the hot path. Fuzzy ("LIKELY") matches are visibly marked.

**UC-2: Runner searches an unknown bib.** A clear "no runner with that number" message. The response is the same whether the bib is unknown or simply has no photos, so nothing leaks.

**UC-3: Organizer onboards an event.**
1. Provide branding: logo, colours, name, date, race distances.
2. Provide the results export from the timing company.
3. Provide photos (ideally originals, not resized).

**UC-4: Operator ingests and reviews.**
1. Run recognition on the GPU machine.
2. Optionally run the Haiku second opinion on uncertain reads.
3. Review in the desktop app, prioritised by uncertainty.
4. Export `bib_export.csv`.

**UC-5: Operator publishes.**
1. Import results and bibs into Supabase.
2. Generate photo derivatives.
3. Upload them to R2.
4. Export the static per-bib files.
5. Push, or trigger a build; Cloudflare builds and deploys.

**UC-6: Takedown or erasure request.** A runner asks for a photo or their data to be removed. A procedure is drafted in `legal/DSAR_AND_TAKEDOWN.md`; today it is a manual database edit plus republish.

**UC-7: Abuse attempt.** A script tries to enumerate bibs 1…N. It must pass Turnstile to get a session, and each session can open at most 30 different bibs. Harvesting a 300-runner field therefore needs about 10 separate Turnstile passes.

---

## 5. System context

```
                ┌─────────────────────────────────────────────────────────┐
                │                    OFFLINE (per event)                  │
                │                                                         │
 Photographers ─┼─▶ photo folder ─▶  Local GPU machine                    │
                │                   ├─ recognition (YOLO + EasyOCR)       │
 Timing company ┼─▶ results.csv     ├─ optional Claude Haiku check ───────┼──▶ Anthropic API
                │                   ├─ review_app.py (human)              │
                │                   └─ import / export / media scripts ───┼──▶ Supabase (Postgres)
                │                                                         │──▶ Cloudflare R2
                └────────────────────────────┬────────────────────────────┘
                                             │ git push
                                             ▼
                                 GitHub (Brca04/MarathonOCR)
                                             │ Workers Builds
                                             ▼
                ┌─────────────────────────────────────────────────────────┐
                │                 ONLINE (Cloudflare edge)                │
 Runner ────────┼─▶ Worker "marathonocr"                                  │
 (browser)      │    ├─ static assets: HTML/JS/CSS, /data/stats.json,     │
                │    │                 /data/bib/<bib>.json               │
                │    ├─ guard: /api/session, /data/bib/*, /media/*        │
                │    └─ R2 binding MEDIA → photos                         │
 Turnstile ◀────┼──── siteverify                                          │
                └─────────────────────────────────────────────────────────┘
                     Supabase find_runner(): fallback only, disabled for
                     statically published events
```

**External dependencies**

| Dependency | Used for | Criticality on race day |
|---|---|---|
| Cloudflare Workers + static assets | Site, search data, guard | **Critical** |
| Cloudflare R2 | Photo files | **Critical** |
| Cloudflare Turnstile | Bot check at session issuance | High: if it is down, new sessions fail. The client degrades with a "busy" message |
| Supabase | Source of truth; build-time export | Low on race day: not on the hot path |
| GitHub | Source and deploy trigger | None on race day |
| Anthropic API | Optional ingest-time second opinion | None on race day |
| utrka.com / timing company | Results data | Ingest time only |

---

## 6. Architecture overview

### 6.1 Architectural style

- **Batch-then-publish (static snapshot).** All expensive and uncertain work happens offline. The published artefact is immutable, cacheable and cheap to serve.
- **Edge-first serving.** A single Cloudflare Worker fronts everything. Static assets bypass it unless they match the guarded paths (`run_worker_first`).
- **Database as system of record, not as serving tier.** Postgres holds normalised data and the matching logic. Its output is pre-computed per bib at publish time.
- **Human in the loop by design.** The pipeline proposes and a human disposes. Confidence calibration decides how much human attention is needed.
- **Pluggable recognition.** Detector and recognizer sit behind interfaces, so models can be swapped and scored against a fixed answer key.

### 6.2 Layer view

| Layer | Technology | Responsibility |
|---|---|---|
| Recognition library | Python 3, PyTorch (CUDA cu128 / MPS), Ultralytics YOLO11, EasyOCR | Detect → crop → deskew/upscale → recognise → ranked candidates |
| Verification (optional) | Anthropic Messages API, `claude-haiku-4-5` | Second opinion on low-confidence crops; whole-photo sweep |
| Review | Streamlit (`review_app.py`) | Human confirmation, autosave, CSV export |
| Ingest tooling | Node.js scripts (`web/scripts/*.mjs`), supabase-js, sharp, wrangler | Import results and bibs, upload or derive photos, export static data, fill R2 |
| System of record | Supabase Postgres 15+ with `pg_trgm`, `fuzzystrmatch`, RLS | Events, races, runners, photos, detections, matching function |
| Web app | Next.js 16 (static export), React 19, TypeScript | Landing, search, runner page, lightbox, legal pages, HR/EN |
| Edge | Cloudflare Worker (TypeScript), static assets, R2, rate-limit bindings, Turnstile | Sessions, guarded data, photo delivery |
| CI/CD | GitHub → Cloudflare Workers Builds | Build + export + deploy on push |

---

## 7. Component design

### 7.1 Recognition library (`src/marathon_ocr/`)

The library is shared by the evaluation harness and production scripts, so **benchmarks and production run the same code path** (crop geometry, normalisation, thresholds).

| Module | Responsibility | Key types |
|---|---|---|
| `dataset.py` | CVAT 1.1 parser for the evaluation set; handles rotated boxes correctly | ground-truth boxes |
| `detectors/base.py` | Finding bib regions | `Detection` (box + confidence), `Detector` (ABC), `PersonDetector`, `TorsoHeuristicDetector`, `YOLOBibDetector`, `WholeImageDetector` |
| `crops.py` | Deskew, pad, upscale crops to a target height | — |
| `recognizers/base.py` | Engine interface and normalisation | `Reading` (**ranked candidate list**, not a string), `Recognizer`, `normalise_digits()` |
| `recognizers/engines.py` | Engine adapters | EasyOCR (digit allowlist), PaddleOCR, TrOCR, VLM |
| `recognizers/cascade.py` | Cheap primary engine, with an expensive fallback below a confidence threshold | `CascadeRecognizer`, `CascadeStats` |
| `pipeline.py` | Orchestrates one photo | `BibPipeline.process(image) → PhotoResult`, `BibHit` |
| `metrics.py` | exact / CER / fuzzy@1, sliced by crop height | — |
| `verify.py` | Claude Haiku second opinion and verdict logic | `HaikuVerifier`, `HaikuRead`, `Verdict`, `judge()` |

**Detector strategies**

| Detector | How it works | Training needed | Status |
|---|---|---|---|
| `WholeImageDetector` | The whole frame is one "box" (a control) | No | Baseline only; fails on small bibs, by design |
| `PersonDetector` | YOLO11 COCO class 0 (person) | No | Works out of the box |
| `TorsoHeuristicDetector` | Person box, then the torso band (≈10–95% of height, ±5% width) | No | **What the Željava run used** |
| `YOLOBibDetector` | Single-class YOLO11 fine-tuned on bib boxes (`models/bib_detector/best.pt`, `imgsz` 1280) | Yes (Roboflow dataset, `scripts/train_bib_detector.py`) | Trained on the RTX 5070 PC; **not yet scored on Željava** |

**Normalisation.** `normalise_digits()` maps common OCR confusions (`O→0`, `l→1`, `S→5`, …) and enforces a 2–6 digit length. It is applied identically everywhere: harness, pipeline, Haiku parser, import.

**Why ranked candidates.** A recognizer returns several candidates with confidences, and *all* are stored (the `detections.rank` column). Collapsing to one string throws away exactly the information the fuzzy-matching tier needs (for example, a truncated `514` for bib `1514`).

### 7.2 Recognition entry points (`scripts/`)

| Script | Purpose |
|---|---|
| `check_env.py` | Verifies the GPU stack with a real matmul. The RTX 5070 is Blackwell sm_120 and needs the cu128 PyTorch build |
| `run.py` | CLI: photo or folder in, bibs out; `--detector whole/person/torso/bib`, `--save-boxes` |
| `make_demo_gallery.py` | Batch run that writes review-app inputs, using `best.pt` by default |
| `ocr_gallery_mac.py` | MPS (Apple Silicon) batch OCR using person → torso. Produced the Željava `ocr_all.jsonl` |
| `train_bib_detector.py`, `resume_bib_training.py` | Fine-tune the single-class bib detector → `models/bib_detector/best.pt` |
| `extract_crops.py`, `eval_recognizers.py`, `calibrate.py`, `eval_end_to_end.py` | Evaluation harness: ground-truth crops, per-engine scores, confidence-vs-accuracy table, photo-level recall and precision |
| `haiku_check.py` | Sends unsure reads (and optionally whole photos) to Haiku; writes `.marathon_ocr_haiku.json` |
| `make_suggestions.py` | Turns OCR output into `.marathon_ocr_suggestions.json` for review pre-fill, keeping start-list bibs at confidence ≥ 0.5 |
| `app.py` | Streamlit playground: drop a photo, see what the pipeline reads |

### 7.3 LLM verification tier (`verify.py`, `haiku_check.py`)

**Purpose:** spend API money only where the local model is unsure, and turn disagreement into a review priority.

```
for each runner crop in a photo:
    best local read ≥ 0.8 confidence  → accept ("confident"); no API call
    otherwise                          → Haiku reads the crop (hint: top-3 local reads)
                                          judge(local, haiku) → verdict
optional: one Haiku call per photo on the whole frame (1568 px) to catch missed runners
```

| Verdict | Meaning | Needs human |
|---|---|---|
| `confident` | Local read ≥ 0.8 | No |
| `agree` | Haiku read one of the local candidates | Only if Haiku marked it "partial" |
| `disagree` | Both read something different, or Haiku sees no bib | Yes |
| `haiku_only` | Local read nothing; Haiku read a bib | Yes |
| `whole_only` | Found only by the whole-photo sweep | Yes |
| `empty` | Neither read anything | No |
| `error` / `model_only` | API failure, or dry run | Yes, or retried next run |

**Design notes**

- The reply is constrained to JSON, parsed tolerantly, and normalised with the same `normalise_digits()`.
- `temperature=0`, `max_tokens=200`, and SDK retries (`max_retries=5`). A failed call never stops the batch and is retried on the next run.
- `--dry-run` estimates the cost without calling the API.
- The API key lives only in the repo-root `.env`, which is git-ignored.

**Status:** implemented and used once. Given the budget constraints (§14), the strategic direction is to use an LLM **only on small crops of the residual uncertain cases, through the Batch API with a per-event cap**, not per photo.

### 7.4 Review application (`review_app.py`)

A Streamlit desktop app the operator runs against the photo folder.

```bash
streamlit run review_app.py -- --folder src/slike
```

| Feature | Detail |
|---|---|
| Inputs | Photos, plus `.marathon_ocr_haiku.json` if present, otherwise `.marathon_ocr_suggestions.json` |
| Prioritisation | Sorted by verdict severity; an "Only photos that need me" filter; a progress counter |
| Per photo | Detected boxes drawn and colour-coded by verdict; each read on its own row with an **Add** button; "not a bib in this race" label (start-list check); free-text add and remove |
| Persistence | **Autosave on every change and on Next/Previous** to `.marathon_ocr_review.json` in the photo folder |
| Output | **Export CSV** → `bib_export.csv` (`image_name,bib_numbers`) |
| macOS | Native folder picker via `osascript` in a subprocess (Tk crashed inside Streamlit) |

Review output is treated as **ground truth**. The Željava answer key (`data/answer_keys/zeljava-2026.*`, 663 photos) came from this app.

### 7.5 Ingest and publish tooling (`web/scripts/`)

| Script (`npm run …`) | Input | Effect |
|---|---|---|
| `import:results` (`import-results.mjs`) | Timing CSV | Upserts `races` and `runners`. Column aliases cover HR/EN/DE exports; `--map` for unknown columns; `--date-order`; `--dry-run` prints the parse |
| `import:bibs` (`import-bibs.mjs`) | `bib_export.csv` (+ optional review JSON) | Upserts `photos` and `detections`. With `--review`, also imports the model's rejected low-confidence reads, so the fuzzy tier can recover truncations |
| `upload:photos` (`upload-photos.mjs`) | Photo folder | Resizes (sharp), optional watermark, uploads previews and originals. **Serial; too slow for 20k photos** |
| `media:r2` (`media-to-r2.mjs`) | Supabase paths, or `--list` file | Copies `/media/<event>/{w,t}/<token>.jpg` into the R2 bucket; can pull from the live site with `--from` |
| `export:static` (`export-static.mjs`) | Supabase (service role) | Calls `export_event()` in pages of 500; writes `public/data/bib/<bib>.json` and `public/data/stats.json` |
| `fetch:brand`, `seed:demo` | — | Self-host brand assets; seed demo data |
| `deploy` | — | `next build && wrangler deploy` |
| `prebuild` (`check-deploy-env.mjs`) | env | Refuses to build a production deploy without Supabase and event config, so a live site can't silently ship demo data |

**Photo derivatives and naming.** Each photo gets:

- a **web** derivative of 1600 px long edge (~250 KB);
- a **thumbnail** of 520 px (~30 KB).

Both are named by an **HMAC of the file name with a private salt** (`/media/zeljava-2026/w/582d485a24beb0bf82a5737f.jpg`), so photos cannot be enumerated and are reachable only via a search result. Originals are kept out of the public path.

### 7.6 Web application (`web/`)

Next.js 16, **static export** (`out/`), no server runtime.

| Route / component | Responsibility |
|---|---|
| `app/page.tsx` | Single-page experience: hero, live counters (from `stats.json`), search, runner view, lightbox, downloads |
| `app/find/` | Search entry route |
| `app/privatnost/`, `app/kontakt/` | Privacy notice (HR/EN, **draft**) and contact |
| `components/Hero.tsx`, `Nav.tsx` | Event branding, language switch |
| `components/SearchForm.tsx` | Bib card styled like a real bib, privacy-consent checkbox |
| `components/RunnerView.tsx` | Result header, course track animation, hand-picked hero photo (`lib/profile-photos.json`), photo grid, "download all" |
| `components/Lightbox.tsx` | Keyboard and swipe viewer, "download original" |
| `lib/data.ts` | **The only place that decides where data comes from**: static file first, then Supabase RPC fallback, then demo data |
| `lib/guard.ts` | Session acquisition; lazy-loads Turnstile only when a site key is configured; render mode interaction-only |
| `lib/event.ts`, `lib/config.ts` | Event and brand config from `NEXT_PUBLIC_*` |
| `lib/i18n.ts`, `lib/format.ts` | HR/EN strings; times, pace, dates, race marks |
| `public/_headers` | CSP, HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy; caching rules |

**Search client flow (`lib/data.ts`)**

```
findRunner(bib):
  ensureSession()                 # POST /api/session (+ Turnstile token if configured)
  GET /data/bib/<bib>.json
     200  → render
     404  → "no runner with that number"   (reason: no_bib)
     401  → session expired → ensureSession(force) → retry once
     429 quota        → new session (Turnstile again) → retry once
     429 rate_limited → "busy, try again"
  if static file missing and db_search enabled → supabase.rpc('find_runner')
```

**Downloads.** A single photo or "download all" fetches each file and saves it as a blob. When `original_path` exists, a 5-minute signed URL from the private originals bucket is used. Otherwise the web derivative is served, as on the Željava demo.

### 7.7 Edge guard Worker (`web/worker/index.ts`)

The Worker runs **only** for `/api/*`, `/data/*` and `/media/*`. Everything else is served straight from the static asset store.

| Route | Behaviour |
|---|---|
| `POST /api/session` | 1. Per-IP limit (`SESSION_PER_IP`). 2. If `TURNSTILE_SECRET` is set, verify `body.token` at Turnstile siteverify; otherwise **403 `challenge`**. 3. If `SESSION_SECRET` is set, issue the cookie `mg_s=<sid>.<exp>.<hmac>` (HttpOnly, Secure, SameSite=Strict, Path=/data, **15 min**); otherwise open mode |
| `GET /data/bib/*` | Verify the HMAC cookie (constant-time compare) → **401 `session`**; per-session and per-IP rate limits (approximate) → **429 `rate_limited`**; **session quota** (Durable Object `SessionQuota`, at most `BIB_QUOTA` = 30 distinct bibs; repeats are free) → **429 `quota`**; fetch the asset; missing → **404 `no_bib`**; response `Cache-Control: private, max-age=300` |
| `GET /data/_*` | 404 (reserved for internal files) |
| `GET/HEAD /media/*` | Serve from R2 (`MEDIA`) with ETag / 304 and `max-age=604800`; rejects `..`; falls back to the asset store |
| other `/api/*` | 404 |

**Design properties**

- **Stateless sessions:** there is no server-side session store. A session is a signed, expiring token. The only per-session state is the quota counter: one small SQLite-backed Durable Object per session, wiped by an alarm when the session expires.
- **Fails open on configuration, never on abuse:** a missing secret degrades protection but doesn't take the site down. A failed check blocks.
- The cookie is scoped to `/data`, so it is never sent with page or media requests.

### 7.8 System of record (Supabase)

Project `gqjahxadfodnmbpetgyh`. Schema in `web/supabase/schema.sql`, applied through migrations. See §8 for tables and §9 for matching.

| Function | Caller | Purpose |
|---|---|---|
| `find_runner(slug, bib, dob default null)` | Browser (fallback) and `export_event` | Runner plus ranked photos; `SECURITY DEFINER` |
| `export_event(slug)` | **Service role only** | `(bib, payload)` rows for every runner, so the static export is byte-identical to live search |
| `event_stats(slug)` | Export / landing page | Counters: photos, finishers, tagged bibs, distance, date |
| `runner_pace(interval, km)` | Internal | min/km string |

### 7.9 CI/CD

- **Workers Builds** is connected to `Brca04/MarathonOCR`, production branch `zeljava-demo`, root directory `web`.
- Build command: `npm run export:static`. Deploy command: `npm run deploy`.
- Build variables: all `NEXT_PUBLIC_*` event and brand settings, the Turnstile site key, and `SUPABASE_SERVICE_ROLE_KEY` as a build secret (needed by the export).
- Runtime secrets on the Worker: `SESSION_SECRET`, `TURNSTILE_SECRET`.
- Every push triggers a build; GitHub shows a "Workers Builds: marathonocr" check run per commit. The 9 most recent commits all built successfully.
- **A data-only change** (a new Supabase import) has no commit, so the operator must retry the latest build or push an empty commit.

---

## 8. Data model

```
events 1───* races
   │            │
   │            └───* runners (race_id)        PII: name, dob, club, nationality, times
   1
   └───* runners (event_id, bib)  ← unique per event
   1
   └───* photos 1───* detections               detections.bib_text ⟶ matched to runners.bib
```

### 8.1 Tables

| Table | Key columns | Notes |
|---|---|---|
| `events` | `slug` (unique), `name`, `edition`, `race_date`, `city`, `first_year`, `published`, `db_search` | `published` gates all public reads. `db_search=false` makes search edge-only |
| `races` | `event_id`, `code` (`marathon`/`half`/`10k`/…), `name`, `distance_km` | One event, several distances (Željava: 21.1 km, 10 km, 3.5 km) |
| `runners` | `event_id`, `race_id`, `bib`, `dob`, `full_name`, `gender`, `category`, `club`, `nationality`, `finish_time`, `chip_time`, `place_overall`, `place_gender`, `place_category`, `status` | **Contains personal data.** RLS on, **no select policy**: invisible to the anon key |
| `photos` | `event_id`, `file_name`, `preview_path`, `thumb_path`, `original_path`, `width`, `height`, `captured_at`, `photographer`, `course_point`, `course_km` | No public read policy. Paths point at R2 or storage |
| `detections` | `photo_id`, `bib_text` (normalised, 2–6 digits), `confidence`, `rank`, `bbox` (jsonb), `crop_height`, `source` (`ocr`/`manual`/`review`) | Every candidate is stored, not just the best one. GIN trigram index on `bib_text`, plus b-tree indexes |

### 8.2 Row-level security summary

| Table | anon / authenticated |
|---|---|
| `events`, `races` | Readable only when `published` |
| `runners`, `photos`, `detections` | **No access.** Only `SECURITY DEFINER` functions read them |
| `export_event()` | Refused unless service role |
| `find_runner()` | Refused for browser roles when `db_search=false` (role read from `request.jwt.claims`, because `current_user` inside a definer function is the owner) |

### 8.3 Static data contract

`/data/bib/<bib>.json` is exactly the `find_runner()` result:

```json
{
  "ok": true,
  "runner": { "bib": "91", "name": "…", "club": "…", "race": "Polumaraton", "race_code": "half",
              "distance_km": 21.0975, "time": "1:22:46", "pace": "3:55",
              "place_overall": 2, "place_category": 1, "category": "MS (2006. – 1992.)",
              "nationality": "CRO", "status": "finished" },
  "photos": [ { "id": "…", "file_name": "0123.jpg", "width": 2738, "height": 1825,
                "preview_path": "/media/zeljava-2026/w/<token>.jpg",
                "thumb_path":   "/media/zeljava-2026/t/<token>.jpg",
                "captured_at": "2026-05-02T07:58:27+00:00",
                "read_as": "91", "match_kind": "exact", "match_score": 1, "course_km": null } ]
}
```

`/data/stats.json`: `{ ok, name, city, photos, finishers, tagged_bibs, distance_km, race_date, edition, first_year, course_record }`.

---

## 9. Search and matching semantics

Matching lives in **one place**, `find_runner()`, and is pre-computed for every bib at export time.

### 9.1 Algorithm (detections-first)

1. Strip non-digits from the query, then look up the published event.
2. Look up the runner by `(event_id, bib)`; unknown → `no_bib`.
3. Optional birthdate check: only when `p_dob` is supplied. It is **currently off** (`p_dob = null`).
4. Build the candidate detections:
   - **Exact:** `bib_text = bib`.
   - **Fuzzy:** Levenshtein distance ≤ 1, only when **all** of these hold:
     - the bib has at least 3 digits (one edit on a 2-digit bib reaches a tenth of the field);
     - the length differs by at most 1;
     - the detection confidence is ≥ 0.30 (below that it is mostly texture);
     - **the misread is not another runner's bib.** Without this rule, a typical Željava gallery held 2 real photos and 27 of neighbours.
5. Score each candidate as `confidence × (1.0 if exact else max(similarity, 0.2))`.
6. Keep one row per photo, preferring an exact match and then the highest score.
7. Return the photos in course order (`course_km`, then `captured_at`, then file name), so the gallery reads like the race. Each photo carries `match_kind` and `match_score`. The UI shows fuzzy matches with a **LIKELY** chip.

### 9.2 Why it is built this way

| Principle | Mechanism |
|---|---|
| A stranger's photo is worse than a missing one | Strict fuzzy rules; exact and fuzzy are never silently mixed |
| Truncation is the dominant OCR error (`1514 → 514`) | Store every candidate, including rejected low-confidence ones, and allow ±1 length |
| Dense bib ranges (1–400) make neighbours plausible | The "not another runner's bib" rule |
| Performance on 20k-photo events | The detections-first query touches only one bib and its neighbours (~5.5–6× faster than photo-first) |

---

## 10. Event lifecycle: end-to-end flow

| Phase | Step | Tool / command | Output |
|---|---|---|---|
| **0. Prepare** | Event config and branding | Build variables in Cloudflare; logos in `web/public/brand/` | — |
| | Load results | `npm run import:results -- --csv results.csv --dry-run`, then without `--dry-run` | `races`, `runners` |
| **1. Recognise** | GPU batch | `python scripts/make_demo_gallery.py …` (bib detector) or `run.py` | OCR jsonl / suggestions |
| | Optional second opinion | `python scripts/haiku_check.py --photos … --ocr … [--dry-run]` | `.marathon_ocr_haiku.json` |
| **2. Review** | Human pass | `streamlit run review_app.py -- --folder <photos>` | `.marathon_ocr_review.json`, `bib_export.csv` |
| **3. Load** | Bibs → DB | `npm run import:bibs -- --csv bib_export.csv --review .marathon_ocr_review.json` | `photos`, `detections` |
| | Photos | Derivatives + `npm run media:r2 -- --event <slug>` | R2 objects |
| **4. Publish** | Static export + deploy | Push to the production branch, or retry the latest build (runs `export:static` then `deploy`) | Live site |
| | Lock the database | `update events set db_search=false, published=true where slug=…` | Edge-only search |
| **5. Operate** | Monitor, takedowns | Cloudflare analytics; manual DB edit + republish | — |

**Re-publishing** is idempotent: imports upsert, the export overwrites, and the deploy replaces assets atomically.

---

## 11. Security, abuse protection and privacy

### 11.1 Threat model

| Threat | Impact | Mitigation | Status |
|---|---|---|---|
| Bulk scraping of galleries by enumerating bibs | Mass collection of photos and names | Turnstile at session issuance; HMAC sessions (15 min); **exact cap of 30 distinct bibs per session** (Durable Object); approximate per-location rate limits | Turnstile and sessions verified live. Quota verified locally; live check pending deploy |
| Enumerating photos directly | Bypasses search | HMAC-named media paths; no listing; no public `photos` read | Done |
| Reading PII via the Supabase anon key | Leak of names and birthdates | RLS with no select policy on `runners`/`photos`/`detections`; definer functions only; `db_search=false` | Done |
| Birthdate brute force | Identity verification bypass | Not applicable while the DOB check is off. If enabled: rate limits plus Turnstile | Pending decision |
| Leaked secrets | Account takeover | Secrets only in Cloudflare/Supabase/`.env`; `.gitignore` covers `.env*`, `.dev.vars` | One API token and one Turnstile secret were exposed during setup and **rotated** |
| XSS / clickjacking | Session theft | Strict CSP, `X-Frame-Options`, HttpOnly + SameSite=Strict cookie scoped to `/data` | Done (`'unsafe-inline'` needed for Next hydration) |
| Hotlinking or abuse of photos | Bandwidth cost | Unguessable URLs; R2 has no egress fees | Acceptable |

### 11.2 Verified behaviour (live tests, 1 Oct 2026)

| Request | Result |
|---|---|
| `POST /api/session` without a token | `403 {"reason":"challenge"}` |
| `POST /api/session` with a fake token | `403 {"reason":"challenge"}` |
| `GET /data/bib/91.json` without a cookie | `401` |
| `GET /data/_anything` | `404` |
| 120 session requests in 15 s from one IP (limit 20/min) | 69 allowed, 51 blocked (first block at about request 30). **The Cloudflare limiter works but is approximate, ~3× the limit** |

### 11.3 Privacy (GDPR)

- **Personal data processed:** name, bib, club, nationality, category, times and placings (public results), plus photos of identifiable people. Birthdate is only stored if the timing company provides it.
- **No biometric processing:** matching is by bib, not by face.
- **Lawful basis and transparency:** the privacy page (`/privatnost/`) is a **draft**. Drafts in `legal/` cover the privacy policy, terms, cookie policy, a DPIA skeleton (a DPIA is likely mandatory), the DSAR and takedown procedure, and a licensing and transfer memo. **None has had legal review.**
- **Data minimisation:** the search requires the exact bib, there is no browse-all, and personal data never reaches the browser except for the searched runner.
- **Open decision:** whether a bib alone is enough to open a gallery, or bib plus birthdate. The schema already supports the birthdate check through `p_dob`.
- **Storage:** Cloudflare only stores the session cookie (functional, no consent needed) and Turnstile's challenge state.

---

## 12. Performance, scalability and capacity

### 12.1 Hot path

| Request | Served by | Typical size | Notes |
|---|---|---|---|
| Page shell, JS, CSS | Static assets (no Worker) | ~7–11 KB HTML + chunks | Immutable caching for `/_next/static/*` |
| `/data/stats.json` | Static asset | ~0.2 KB | Short browser cache |
| `/api/session` | Worker (+ Turnstile siteverify) | tiny | Once per 15 minutes per visitor |
| `/data/bib/<bib>.json` | Worker → Durable Object (quota) → asset | 2–5 KB | `private, max-age=300`; one DO call adds a few ms |
| Thumbnails / web photos | Worker → R2 | ~30 KB / ~250 KB | `max-age=604800`, ETag/304 |

Measured page loads were 0.4–0.8 s from the test location.

### 12.2 Capacity reasoning for "10k concurrent users"

- **Static assets** on Cloudflare have no request limit or per-request cost.
- **Worker invocations:** the free plan gives 100k per day; the paid plan ($5/month) gives 10M per month included. A visitor costs roughly 1 session + 1–3 bib lookups + about 20–60 photo requests (grid thumbnails plus opened photos). Because `/media/*` goes through the Worker, **photos dominate Worker usage**. For a 10k-visitor race day, plan on the **Workers Paid plan**.
- **R2:** class B reads are cheap with no egress cost. 20k photos × 2 derivatives ≈ 40k objects, about 6 GB.
- **Database:** not on the hot path, so its size doesn't limit capacity.
- **Not yet done:** a distributed load test (§20).

### 12.3 Ingest throughput

| Stage | Throughput (measured or estimated) |
|---|---|
| EasyOCR on RTX 5070 | ~10 ms per crop (111 ms on CPU). About 60k crops per 20k photos, so ≈ 10 minutes |
| Bib detector (YOLO11, imgsz 1280) on RTX 5070 | Tens of photos per second (to be measured) |
| Human review | Bounded by the share of photos flagged. The goal of the recognition work is to shrink that share |
| Photo upload | **Serial today.** Needs parallelising for 20k photos |

---

## 13. Recognition quality: what has been measured

### 13.1 Evaluation assets

| Asset | Size | Use |
|---|---|---|
| `archive/annotations.xml` (CVAT) | 30 photos, 146 bib boxes | Recognizer benchmark on ground-truth crops (pessimistic: downscaled images, median bib 19 px) |
| `data/answer_keys/zeljava-2026.{csv,json}` | 663 photos, 514 photo–bib pairs, human-reviewed | **End-to-end scoring of any pipeline on a real event** |
| Start list | 310 bibs, range 1–400 | Validity constraint |

### 13.2 Recognizer on perfect crops (CVAT set, EasyOCR)

| Bucket | n | Exact | Fuzzy@1 |
|---|---:|---:|---:|
| All | 146 | 78.8% | **91.1%** |
| Large crops (≥ 40 px) | 17 | 82.4% | **100%** |

**Confidence calibration:** every read with confidence ≥ 0.8 was within one edit of the truth. With a cascade at threshold 0.4, 90.4% of reads are accepted at 98.5% fuzzy@1.

### 13.3 End to end on Željava (person → torso → EasyOCR stand-in)

> **Caveat.** This run used the generic person detector (`yolo11n.pt`), **not** the trained bib detector, on images downscaled to 2000 px and skipping people under 80 px tall. These numbers score that stand-in, not the intended pipeline.

| Outcome over 514 answer-key pairs | Share |
|---|---:|
| Found | 66% |
| Seen but misread or low confidence | 11% |
| **Never seen** (detection failure; 54 of these in photos with zero reads) | **23%** |

| Precision of surfaced reads | Precision | Recall |
|---|---:|---:|
| Confidence ≥ 0.5 | 70.8% | — |
| ≥ 0.5 + start-list filter | 78.7% | — |
| ≥ 0.8 + start-list filter | 89.5% | 59.7% |

**Interpretation:** recognition is close to solved on readable crops; **detection is the bottleneck**. The published Željava data is the human-reviewed result, not raw model output.

---

## 14. Cost model

### 14.1 Fixed and platform costs (per month)

| Item | Cost |
|---|---|
| Cloudflare Workers | Free plan for testing; **$5/month paid plan recommended for events** |
| Cloudflare R2 | ~6 GB per 20k-photo event: well under $1/month storage; no egress fees |
| Turnstile | Free |
| Supabase | Free tier is sufficient (not on the hot path). Free projects pause when idle, so ingest must wake it |
| GPU | Owned hardware (RTX 5070) |

### 14.2 Variable recognition cost per 20k-photo event

| Strategy | API cost |
|---|---|
| Local only (detector + OCR + start list + bursts) | **$0** |
| Claude on ~10% residual uncertain **crops**, through the Batch API (50% off) | **~$5–15** |
| Haiku on every crop below 0.8 plus a whole-photo sweep (as implemented) | ~$40–60 |
| A frontier vision model on every full photo | ~$240 |

Image tokens ≈ ⌈w/28⌉ × ⌈h/28⌉, so **a small crop costs ~50× less than a full photo**. That is why the design sends crops, never whole frames, and only for the residue.

---

## 15. Deployment and operations

### 15.1 Environments

| Environment | Where | Data |
|---|---|---|
| Local dev | `npm run dev` (http://localhost:3000) | Bundled demo event when Supabase is not configured |
| Production | Worker `marathonocr` at `marathonocr.bruno-cavor.workers.dev` | Željava 2026 |

### 15.2 Runbook

| Task | How |
|---|---|
| Deploy code | Push to `zeljava-demo`; watch the GitHub check run |
| Republish data after an import | Dashboard → Workers & Pages → marathonocr → Deployments → latest build → **Retry build** (or push an empty commit) |
| Rotate the session secret | `npx wrangler secret put SESSION_SECRET` (signs out existing sessions; they re-acquire automatically) |
| Rotate Turnstile | Turnstile → widget → Rotate secret key, then `npx wrangler secret put TURNSTILE_SECRET` **immediately** |
| Fill or refresh R2 | `npm run media:r2 -- --event <slug>` (after `npx wrangler login`) |
| Takedown | Delete the detections or photo rows in Supabase → republish. Remove the R2 objects if required |
| Emergency: block search | Remove the site key at build or set a strict limit; or take `/data/bib/*` offline by deploying a guard that returns 503 |

### 15.3 Gotchas learned

- `wrangler secret put <NAME>`: the argument is the **name**; the value is entered at the prompt.
- Secrets used by the Worker must be **runtime** secrets, not build variables.
- Build variables are snapshotted per build. Changing one does nothing until the next build.
- RTX 5070 (sm_120) needs the cu128 PyTorch wheel; `check_env.py` verifies it with a real kernel.
- Next.js 16 needs Node 22 (`web/.node-version`).

---

## 16. Configuration reference

### 16.1 Build-time (`NEXT_PUBLIC_*`, visible in the browser)

| Variable | Example | Purpose |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` / `_ANON_KEY` | project URL / publishable key | Fallback RPC and stats |
| `NEXT_PUBLIC_EVENT_SLUG` | `zeljava-2026` | Which event this deployment serves |
| `NEXT_PUBLIC_EVENT_NAME`, `_NAME_EN`, `_CITY`, `_DATE`, `_EDITION` | — | Copy and headings (`_EDITION=none` hides it) |
| `NEXT_PUBLIC_EVENT_ACCENT`, `_THEME` | — | Colour scheme |
| `NEXT_PUBLIC_EVENT_RACE_BADGE`, `_RACE_LABEL` | `3 UTRKE`, `21,1 km · 10 km · 3,5 km` | Bib-card labels |
| `NEXT_PUBLIC_EVENT_TZ` | `Europe/Zagreb` | Time display |
| `NEXT_PUBLIC_HERO_IMAGE` | `/media/zeljava-2026/w/<token>.jpg` | Landing hero |
| `NEXT_PUBLIC_BRAND_MARK`, `_MARK_RATIO`, `_ICON`, `_APPLE_ICON` | `/brand/zeljava-logo.png`, `606 / 313` | Logo and icons |
| `NEXT_PUBLIC_TURNSTILE_SITEKEY` | `0x4AAAAAAFCxDpHVQwgjiD_B` | Enables Turnstile on the client |

### 16.2 Build secrets

| Secret | Purpose |
|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | `export:static` reads every runner through `export_event()` |

### 16.3 Worker runtime secrets and bindings

| Name | Kind | Purpose |
|---|---|---|
| `SESSION_SECRET` | Secret | HMAC key for `mg_s` session tokens |
| `TURNSTILE_SECRET` | Secret | Turnstile siteverify |
| `ASSETS` | Assets binding | Static files (`out/`) |
| `MEDIA` | R2 binding | Bucket `marathonocr-media` |
| `BIB_PER_SESSION` | Rate limit (4101) | 20 requests per 60 s |
| `BIB_PER_IP` | Rate limit (4102) | 120 requests per 60 s |
| `SESSION_PER_IP` | Rate limit (4103) | 20 requests per 60 s |
| `QUOTA` | Durable Object (`SessionQuota`, migration `v1`) | Exact per-session cap on distinct bibs |
| `BIB_QUOTA` | Variable (in `wrangler.jsonc`) | Distinct bibs per session, default `30` |

### 16.4 Ingest (`.env` in the repo root, never committed)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Haiku verifier |
| `MARATHON_HAIKU_MODEL` | Override the model (default `claude-haiku-4-5`) |

---

## 17. Repository layout

```
MarathonOCR/
├─ src/marathon_ocr/          recognition library (§7.1)
│  ├─ detectors/              person / torso / bib / whole-image detectors
│  ├─ recognizers/            engines, cascade, Reading, normalise_digits
│  ├─ crops.py  dataset.py  metrics.py  pipeline.py  verify.py
├─ scripts/                   recognition, training, evaluation, Haiku, suggestions (§7.2)
├─ review_app.py              Streamlit review tool (§7.4)
├─ app.py                     Streamlit pipeline playground
├─ archive/annotations.xml    CVAT evaluation set (30 photos)
├─ data/answer_keys/          zeljava-2026.csv / .json (663 photos)
├─ docs/                      Croatian PDF documentation, pitch PPTX
├─ legal/                     privacy, terms, cookies, DPIA, DSAR/takedown, licensing memo (drafts)
├─ web/
│  ├─ app/  components/  lib/ Next.js site (§7.6)
│  ├─ worker/index.ts         edge guard (§7.7)
│  ├─ supabase/schema.sql     schema, RLS, functions (§8, §9)
│  ├─ scripts/                import / export / media / deploy tooling (§7.5)
│  ├─ public/_headers         security headers and caching
│  └─ wrangler.jsonc          Worker config, bindings, rate limits
└─ (git-ignored) models/, src/slike/, .venv*/, _transfer/, web/public/{data,media}/, .env*
```

---

## 18. Architecture decision records

**ADR-1: Batch ingest on a local GPU, not cloud inference.** *Context:* the event is a one-off batch; owned RTX 5070. *Decision:* run recognition locally. *Consequences:* zero GPU cost and no autoscaling, but the operator must have the machine and the photos locally.

**ADR-2: Publish a static snapshot per bib.** *Context:* race-day spikes, small database tier. *Decision:* pre-compute `find_runner()` for every bib at publish time and serve it as JSON files from the edge. *Consequences:* capacity independent of the database, and identical semantics because the export calls the same function. Data changes need a rebuild.

**ADR-3: Matching logic lives in Postgres.** *Decision:* one `SECURITY DEFINER` function is the single definition of "which photos belong to bib X". *Consequences:* one place to tune precision; the static export and the live fallback can never diverge.

**ADR-4: Store all recognizer candidates.** *Decision:* the `detections` table keeps ranked alternatives and rejected low-confidence reads. *Consequences:* the fuzzy tier can recover truncations, at the cost of more rows (cheap).

**ADR-5: Precision over recall in fuzzy matching.** *Decision:* strict fuzzy rules, including "a misread must not be another runner's bib", with fuzzy results labelled LIKELY. *Consequences:* some recoverable photos are missed; no neighbour-flooding.

**ADR-6: A human in the loop is a feature.** *Decision:* calibrated confidence decides what a human must see; the review app is a first-class component. *Consequences:* publishable quality today; the recognition roadmap is measured by *review minutes per event*, not only by accuracy.

**ADR-7: LLMs only on crops of the residue.** *Context:* the budget can't cover per-photo LLM calls. *Decision:* the LLM is an optional, capped fallback on small crops through the Batch API. *Consequences:* predictable cost of a few dollars per event.

**ADR-8: Edge guard with stateless sessions, Turnstile and a session quota.** *Decision:* HMAC session cookies (15 min), Turnstile at issuance, an exact cap of 30 distinct bibs per session, unguessable media URLs, and a database closed to browsers. *Why a quota, not only a rate:* a perfect 20/min limit still allows ~300 lookups in a 15-minute session, which is a whole small event; a total cap per session forces a new Turnstile pass every 30 bibs. *Consequences:* no server state. It fails open on missing configuration, which is acceptable for availability but must be monitored.

**ADR-9: One deployment per event.** *Decision:* event selection by build variables. *Consequences:* simple and isolated, but N events means N deployments (or future multi-tenant work).

**ADR-10: No face recognition.** *Decision:* match by bib only. *Consequences:* avoids biometric processing under GDPR Art. 9; runners with hidden bibs are found only through review or burst linking.

---

## 19. Known limitations and risks

| # | Limitation / risk | Severity | Mitigation / plan |
|---|---|---|---|
| L1 | Cloudflare rate-limit bindings are approximate (~3× the limit gets through) | Low (now) | Exact per-session quota added (Durable Object). WAF rate-limit rule possible once on a custom domain |
| L2 | **Automatic detection misses ~23% of bibs** (stand-in detector); the trained bib detector is unmeasured | High | Score `best.pt` at full resolution against the Željava answer key; tiling; burst linking |
| L3 | **Ultralytics YOLO is AGPL-3.0**; the Enterprise licence price is not public | Medium (commercial) | Licence it, or move to an Apache-2.0 detector (RF-DETR, YOLOX) |
| L4 | **Legal documents are drafts**; DPIA not done; bib-only access decision pending | High before commercial use | Counsel review; decide on the birthdate check |
| L5 | Data changes need a manual rebuild | Low | One-command publish or a deploy hook |
| L6 | `upload-photos.mjs` is serial | Medium for 20k+ events | Worker pool |
| L7 | One event per deployment | Low | Multi-tenant routing later |
| L8 | `workers.dev` domain | Low (trust) | Custom domain |
| L9 | No load test performed | Medium | Distributed test before selling the "10k concurrent" claim |
| L10 | Supabase free tier pauses when idle | Low | Wake it before ingest, or upgrade |
| L11 | Single operator; the pipeline runs on one person's machines | Medium | Documentation (this file), scripted runbooks |
| L12 | Fails open when secrets are missing | Low | Deploy checklist; the live tests in §11.2 |

---

## 20. Roadmap

### 20.1 Recognition: accuracy at low cost (highest priority)

1. **Baseline:** run the trained bib detector (`best.pt`) at full resolution on Željava; score it with the answer key (found / misread / never seen / precision).
2. **Detector:**
   - Run on overlapping tiles at full resolution, and remove the 80 px cutoff.
   - Auto-label bib boxes from the answer key to retrain.
   - Evaluate an Apache-2.0 detector.
3. **Reader:**
   - Fine-tune a scene-text recognizer (PARSeq, Apache-2.0) on bib crops plus synthetic bibs.
   - **Start-list constraint:** snap a read to the nearest valid bib only when it is unambiguous.
4. **Burst linking:** carry a confirmed bib to neighbouring frames (same camera, EXIF time seconds apart, similar clothing), flagged for review.
5. **Capped LLM fallback** on residual crops through the Batch API.
6. **Every change is scored against the answer key** before adoption.

### 20.2 Review speed

- Group bursts so a runner is confirmed once across several frames.
- Review crop strips instead of full photos.
- Keyboard-first flow, and show only flagged photos.

### 20.3 Platform and launch readiness

- Confirm the session quota on the live site after deploy.
- Custom domain plus a WAF rule (L8).
- A final privacy decision and legal review (L4).
- One-command publish (L5).
- A parallel uploader (L6).
- A distributed load test (L9).
- A real-visitor Turnstile check on mobile data and venue Wi-Fi.

---

## 21. Glossary

| Term | Meaning |
|---|---|
| **Bib** | The numbered race tag pinned to a runner's chest |
| **Detection** | A region believed to contain a bib, or a stored bib-candidate row in the database |
| **Reading** | A recognizer's ranked list of candidate strings with confidences |
| **fuzzy@1** | A read counts as correct if it is within Levenshtein distance 1 of the truth |
| **Cascade** | Cheap recognizer first; an expensive one only below a confidence threshold |
| **Answer key** | Human-confirmed list of the bibs in each photo of an event; the scoring ground truth |
| **Start list** | Every bib issued for the event; reads outside it are invalid |
| **Static export** | The per-bib JSON files generated from `export_event()` at publish time |
| **Guard** | The Cloudflare Worker that protects `/api`, `/data` and `/media` |
| **Turnstile** | Cloudflare's CAPTCHA-free bot check |
| **R2** | Cloudflare object storage with no egress fees |
| **RLS** | Postgres row-level security |
| **LIKELY** | UI label for a fuzzy (one-edit) photo match |
