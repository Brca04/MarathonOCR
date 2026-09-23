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

Add `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` and
`NEXT_PUBLIC_EVENT_SLUG` as build-time environment variables. **Do not add the
service role key** — nothing in the build needs it.

`wrangler pages deploy out` does the same thing from the command line.

---

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

- **No rate limiting on `find_runner`.** A determined attacker with a bib list
  could brute-force birthdates. Supabase's rate limits or a Cloudflare Turnstile
  on the form closes that before a public launch.
- **`upload-photos.mjs` is serial.** Fine for a few hundred photos, slow for
  20k; parallelise with a small worker pool when that day comes.
