# Zagreb Marathon — photo search

The runner-facing half of MarathonOCR. Three screens, ported from the design
file: landing, bib + birthdate search, and the runner's gallery with a lightbox.

```
local GPU batch job  →  bib_export.csv  ─┐
timing company       →  results.csv     ─┼→  scripts/*.mjs  →  Supabase
photographers        →  folder of JPEGs ─┘                        ↓
                                              Next.js static export → Cloudflare Pages
```

Ingest is an offline batch you run per event. The site itself is a static
export — no server, no edge functions, no adapter — so a deploy is a folder of
files and matching Cloudflare's free tier costs nothing but bandwidth.

---

## Run it now

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

With no environment configured it runs on bundled demo data. Go to **Find my
photos** → *View a demo runner (bib 1042)*, or type bib `1042` and birthdate
`14 · 03 · 1989`.

## Wire it to Supabase

1. Create a project at supabase.com.
2. SQL editor → paste **`supabase/schema.sql`** → run. It creates the tables,
   the trigram index, RLS, the two RPCs and both storage buckets.
3. Copy `.env.example` to `.env.local` and fill in the project URL, the anon
   key and the service role key.
4. Seed something to look at:

```bash
npm run seed:demo        # the three demo runners, in your real database
```

Restart `npm run dev` and the same search now goes through Postgres.

## Load a real event

```bash
# 1. Runners and results. Check the column mapping first — it prints what it
#    matched and never writes on a dry run.
node scripts/import-results.mjs --csv ../results.csv --dry-run
node scripts/import-results.mjs --csv ../results.csv

# 2. The review app's export: which bibs are in which photo.
node scripts/import-bibs.mjs --csv "C:/photos/zagreb-2026/bib_export.csv" \
                             --review "C:/photos/zagreb-2026/.marathon_ocr_review.json"

# 3. The photos themselves.
npm i -D sharp                     # optional, but resizes instead of uploading 6000px files
node scripts/upload-photos.mjs --dir "C:/photos/zagreb-2026" --originals --watermark
```

**`--dry-run` on the first two prints the parse and stops.** Do that before the
first real import of any new timing provider's export.

### The results CSV

Column names are matched against a list of aliases in English and Croatian —
`bib`/`startni broj`/`StartNo`, `dob`/`datum rođenja`/`Born`, `time`/`rezultat`,
and so on. Most exports need no flags. When one column is named something the
list does not know:

```bash
node scripts/import-results.mjs --csv results.csv --map bib=Nr,dob=Geburtsdatum
```

Dates are read as day-month-year; pass `--date-order mdy` for a US export.
Rows with only a birth *year* are imported but flagged — they cannot pass the
birthdate check, so those runners will not be able to find their photos.

### The bib export

`review_app.py` writes `image_name,bib_numbers`. Pointing `--review` at the
progress JSON in the same folder also imports the model's *rejected* reads at
low confidence. That is deliberate: a truncated read like `1514 → 514` is the
dominant OCR failure, and having it in the table is what lets the
edit-distance-1 tier surface the photo anyway.

Course points come from the file name when the photographers use prefixes
(`finish_0412.jpg`, `10k_0088.jpg`). Otherwise pass `--point Finish --km 42.195`
per folder, or a metadata CSV with `--meta points.csv`
(`file_name,course_point,course_km,photographer,captured_at`).

---

## Deploy to Cloudflare Pages

Cloudflare dashboard → Workers & Pages → Create → Pages → connect the repo.

| Setting | Value |
|---|---|
| Framework preset | None |
| Build command | `npm run build` |
| Build output directory | `out` |
| Root directory | `web` |

Node comes from `web/.node-version` (22). Next 16 does not build on Pages' older
default.

### Environment variables

Set these under Settings → Environment variables, **for both Production and
Preview** — a preview branch without them builds the demo event.

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | your project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the anon key |
| `NEXT_PUBLIC_EVENT_SLUG` | e.g. `zagreb-2026` |
| `NEXT_PUBLIC_BRAND_MARK` | `/brand/znak.jpg` once self-hosted (see below) |
| `NEXT_PUBLIC_BRAND_ICON` | `/brand/znak-150.jpg` |
| `NEXT_PUBLIC_EVENT_TZ` | optional, see `.env.example` |

**Do not add the service role key** — nothing in the build needs it, and every
`NEXT_PUBLIC_` value is visible in the browser.

The build refuses to run on Pages without the first three
(`scripts/check-deploy-env.mjs`). That is deliberate: the app falls back to the
bundled demo event when Supabase is unconfigured, and a live site serving three
invented runners as real results is worse than a red build. For a throwaway test
site before Supabase exists, set `ALLOW_DEMO_BUILD=1` and the build proceeds with
a warning.

### Before the first deploy

```bash
npm run fetch:brand    # saves the race emblem into public/brand/
```

then set `NEXT_PUBLIC_BRAND_MARK` / `NEXT_PUBLIC_BRAND_ICON` to the local paths.
Without it the header mark and favicon are hotlinked from
`www.zagreb-marathon.com`, which makes the site depend on someone else's server
staying up — and it needs that host in the `img-src` of `public/_headers`.

### Headers

`public/_headers` ships with the export and Cloudflare applies it at the edge:
CSP, HSTS, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, plus
immutable caching for `/_next/static/*`. Read the comments at the top before
tightening it — in particular, `script-src` needs `'unsafe-inline'` for Next's
hydration payload, and adding a hash there would silently disable it.

### Checking a build the way Pages serves it

```bash
npm run build
npx serve out          # or any static server
```

`wrangler pages deploy out --project-name=<project>` deploys the same folder
from the command line.

---

## Race-day traffic: publish static, keep the database as a fallback

A search used to be one Postgres call. At ~60 searches/s on the smallest
Supabase instance that is fine for a few thousand visitors and not for a
post-race rush. So publishing now has one extra step:

```bash
npm run export:static      # writes public/data/stats.json + public/data/bib/<bib>.json
npm run deploy             # next build + wrangler deploy
```

`export:static` calls `export_event()` (service role only) and writes exactly
what `find_runner()` would have returned, one 2–5 KB file per bib. The site
fetches `/data/bib/<bib>.json` first; Cloudflare serves static assets without
a request limit, so search capacity no longer depends on the database. A bib
missing from the export falls through to `find_runner()`, which is still there
and is now detections-first (~5.5× faster than before on a 20k-photo event).

Photos follow the same rule: the grid loads a ~30 KB thumbnail (`thumb_path`),
the viewer the ~250 KB web-size preview. For a test event they ship as static
assets under `/media/<event>/`; Workers allows 20,000 asset files on the free
plan, so a real 20k-photo event should put `/media` on R2 (no egress fees) and
point `preview_path`/`thumb_path` at it.

Re-run `export:static` + `deploy` after every import; `/data/*` is cached for a
minute at the browser, so a republish is visible almost at once.

## Bot and scraper protection

Static per-bib files would let anyone download every gallery by counting
1..10000. Four layers stop that without slowing a runner down:

1. **Edge guard** (`worker/index.ts`) runs only for `/data/*` and `/api/*`.
   A bib lookup needs a signed session cookie from `POST /api/session`, and is
   rate limited per session (20/min) and per IP (120/min — race-day Wi-Fi puts
   many phones behind one address). `/data/_*` is never served.
2. **Cloudflare Turnstile** (optional, recommended): with
   `NEXT_PUBLIC_TURNSTILE_SITEKEY` at build time and `TURNSTILE_SECRET` as a
   Worker secret, a session is only issued after an invisible bot check.
   Create the widget under Cloudflare → Turnstile → Add site (mode: Managed).
3. **Unguessable photo URLs**: previews and thumbnails are named by an HMAC of
   the file name, so photos can only be found through a search.
4. **Database is edge-only**: for a statically published event set
   `events.db_search = false`; `find_runner()` then refuses browser callers,
   and `photos`/`detections` have no public read policy at all.

```bash
npx wrangler secret put SESSION_SECRET      # once: any long random string
npx wrangler secret put TURNSTILE_SECRET    # optional, from the Turnstile widget
```

Only `/data/*` and `/api/*` count as Worker requests (free plan: 100,000 a
day, roughly 30,000 visitors). For a big event, the $5/month Workers Paid plan
raises that to 10 million.

## How the pieces fit

### Matching, and why fuzzy is worth having

`find_runner()` collects a photo when any detection on it either reads the bib
exactly, or is one edit away and of a plausible length. Each photo is scored
`confidence × similarity` and carries `match_kind`, which the gallery renders as
a small **LIKELY** chip. Exact and fuzzy hits are never silently mixed: a missed
photo annoys a runner, a stranger's photo in their gallery is worse.

The repo's own numbers are the argument — 78.8% exact against 91.1% at
edit-distance-1 on the same reads. That +12 points is a `gin_trgm_ops` index and
a `levenshtein()` call, not a better model.

### Why birthdates never reach the browser

`runners` has RLS on and **no** select policy, so the anon key sees zero rows.
The only way in is `find_runner(slug, bib, dob)`, a `SECURITY DEFINER` function
that returns a runner only when both halves match. Nothing can enumerate the
field, and a scraper with the anon key learns nothing about who ran.

That is also why the site can be a static export: the check that needs to be
trusted runs in Postgres, not in a Node server we would otherwise have to host.

### Storage

Two buckets. `race-previews` is public and holds the web-sized (optionally
watermarked) JPEG. `race-originals` is private; the app asks for a 5-minute
signed URL when a runner downloads an original. Swapping either for Cloudflare R2 is a
change to `previewUrl()` and `signedOriginalUrl()` in `lib/supabase.ts` and
nothing else.

### Layout

```
app/
  page.tsx            landing — hero, animated counters
  find/page.tsx       search ↔ runner state, lightbox, downloads, toasts
components/
  Nav.tsx             sliding pill
  SearchForm.tsx      the bib card + birthdate field
  RunnerView.tsx      hero, course track animation, photo grid
  Lightbox.tsx        keyboard-navigable viewer
lib/
  data.ts             the only place that decides Supabase vs demo
  demo.ts             bundled event, so a fresh clone runs with no keys
  format.ts           times, dates, pace, course marks
  supabase.ts         client + storage URL resolution
supabase/schema.sql   tables, RLS, find_runner(), event_stats()
scripts/              importers, all with --dry-run
```

Component styles are inline, exactly as they came out of the design file, so the
two can be diffed when the design changes. Only the keyframes, media queries and
`:hover` rules live in `app/globals.css`.

---

## Known gaps

- **No rate limiting on the `find_runner` fallback.** A determined attacker with a bib list
  could brute-force birthdates. Supabase's rate limits or a Cloudflare Turnstile
  on the form closes that before a public launch.
- **`upload-photos.mjs` is serial.** Fine for a few hundred photos, slow for
  20k; parallelise with a small worker pool when that day comes.
