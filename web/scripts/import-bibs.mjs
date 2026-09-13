#!/usr/bin/env node
/**
 * Import the review app's export into `photos` + `detections`.
 *
 * The CSV that `review_app.py` writes is one row per photo:
 *
 *     image_name,bib_numbers
 *     ZG26_0412.jpg,"1042, 2318"
 *
 * Usage:
 *   node scripts/import-bibs.mjs --csv "C:/photos/bib_export.csv"
 *   node scripts/import-bibs.mjs --csv bib_export.csv --review "C:/photos/.marathon_ocr_review.json"
 *   node scripts/import-bibs.mjs --csv bib_export.csv --point Finish --km 42.195
 *   node scripts/import-bibs.mjs --csv bib_export.csv --meta points.csv
 *
 * Human-confirmed numbers land as source='review' with confidence 1.0. If you
 * point --review at the progress JSON, the model's own reads come in too as
 * source='ocr' — that is what lets the fuzzy tier catch a truncated read like
 * 1514 → 514 that the reviewer never had to fix by hand.
 */
import fs from 'node:fs';
import { parse } from 'csv-parse/sync';
import {
  admin,
  args,
  DEFAULT_SLUG,
  die,
  digits,
  ensureEvent,
  log,
  normaliseRow,
  pick,
  readCsv,
  upsertBatched,
} from './lib.mjs';

const a = args();
if (!a.csv) die('Pass --csv <path to bib_export.csv>.');
const slug = a.event || DEFAULT_SLUG;
const dryRun = Boolean(a['dry-run']);

/** Course point from the file name when the photographers use prefixes. */
const POINT_PATTERNS = [
  [/(^|[^a-z])start/i, 'Start', 0],
  [/(^|[^0-9])5\s?k/i, '5K', 5],
  [/(^|[^0-9])10\s?k/i, '10K', 10],
  [/half|polumaraton|21\s?k/i, 'Half', 21.0975],
  [/(^|[^0-9])30\s?k/i, '30K', 30],
  [/(^|[^0-9])35\s?k/i, '35K', 35],
  [/finish|cilj|medal/i, 'Finish', 42.195],
];

function inferPoint(fileName) {
  for (const [re, point, km] of POINT_PATTERNS) {
    if (re.test(fileName)) return { course_point: point, course_km: km };
  }
  return { course_point: a.point || null, course_km: a.km ? Number(a.km) : null };
}

log.step(`Reading ${a.csv}`);
const rows = parse(readCsv(a.csv), {
  columns: true,
  skip_empty_lines: true,
  bom: true,
  trim: true,
}).map(normaliseRow);
if (!rows.length) die('No data rows found.');

// Optional per-photo metadata: file_name,course_point,course_km,photographer,captured_at
const meta = new Map();
if (a.meta) {
  for (const r of parse(readCsv(a.meta), { columns: true, skip_empty_lines: true, bom: true, trim: true }).map(
    normaliseRow,
  )) {
    const name = pick(r, ['file_name', 'image_name', 'filename', 'image']);
    if (name) meta.set(name, r);
  }
  log.info(`${meta.size} metadata row(s) from ${a.meta}`);
}

// Optional: the review app's progress file, which also keeps the raw model reads.
let review = {};
if (a.review) {
  if (!fs.existsSync(a.review)) die(`No such file: ${a.review}`);
  review = JSON.parse(fs.readFileSync(a.review, 'utf8'));
  log.info(`${Object.keys(review).length} review entr(ies) from ${a.review}`);
}

const photos = [];
const detections = []; // resolved to photo ids after the photo upsert
let confirmedCount = 0;
let ocrOnlyCount = 0;

for (const row of rows) {
  const fileName = pick(row, ['image_name', 'file_name', 'filename', 'image', 'photo']);
  if (!fileName) continue;

  const bibField = pick(row, ['bib_numbers', 'bibs', 'bib_number', 'numbers', 'bib']);
  // Human-confirmed numbers keep single digits — elite fields hand out bib "7".
  // Model candidates below are held to two digits, where a stray "3" from a
  // sponsor logo would otherwise fuzzy-match half the field.
  const confirmed = bibField
    .split(/[,;|\s]+/)
    .map((x) => digits(x))
    .filter((x) => x.length >= 1);

  const m = meta.get(fileName) || {};
  const inferred = inferPoint(fileName);
  const capturedRaw = pick(m, ['captured_at', 'timestamp', 'time', 'datetime']);

  photos.push({
    file_name: fileName,
    course_point: pick(m, ['course_point', 'point']) || inferred.course_point,
    course_km: Number(pick(m, ['course_km', 'km'])) || inferred.course_km,
    photographer: pick(m, ['photographer', 'author', 'photo_by']) || a.photographer || null,
    captured_at: capturedRaw ? new Date(capturedRaw).toISOString() : null,
    width: Number(pick(m, ['width'])) || null,
    height: Number(pick(m, ['height'])) || null,
  });

  const perPhoto = new Map();
  for (const bib of confirmed) {
    perPhoto.set(bib, { bib_text: bib, confidence: 1.0, rank: 0, source: 'review' });
    confirmedCount++;
  }

  // Model candidates the reviewer removed are still worth keeping: a wrong read
  // of a real bib is exactly what edit-distance-1 matching is for. They go in at
  // a lower rank so an exact confirmed hit always outranks them.
  const modelNumbers = review[fileName]?.model_numbers ?? [];
  for (const raw of modelNumbers) {
    const bib = digits(raw);
    if (!bib || bib.length < 2 || perPhoto.has(bib)) continue;
    perPhoto.set(bib, { bib_text: bib, confidence: 0.35, rank: 1, source: 'ocr' });
    ocrOnlyCount++;
  }

  detections.push({ fileName, reads: [...perPhoto.values()] });
}

log.step('Parsed');
log.info(`${photos.length} photos`);
log.info(`${confirmedCount} confirmed bib read(s), ${ocrOnlyCount} extra model candidate(s)`);
const tagged = detections.filter((d) => d.reads.some((r) => r.source === 'review')).length;
log.info(`${tagged} photo(s) have at least one confirmed bib, ${photos.length - tagged} have none`);
const distinct = new Set(detections.flatMap((d) => d.reads.map((r) => r.bib_text)));
log.info(`${distinct.size} distinct bib number(s)`);

if (dryRun) {
  console.table(
    detections.slice(0, 5).map((d) => ({
      file: d.fileName,
      bibs: d.reads.filter((r) => r.source === 'review').map((r) => r.bib_text).join(' '),
      extra: d.reads.filter((r) => r.source === 'ocr').map((r) => r.bib_text).join(' '),
    })),
  );
  log.step('Dry run — nothing written.');
  process.exit(0);
}

const db = admin();
const { event } = await ensureEvent(db, slug);

log.step(`Writing to event ${slug}`);
await upsertBatched(
  db,
  'photos',
  photos.map((p) => ({ ...p, event_id: event.id })),
  'event_id,file_name',
);

// Fetch ids back so detections can be replaced wholesale for these photos.
const { data: stored, error } = await db
  .from('photos')
  .select('id,file_name')
  .eq('event_id', event.id);
if (error) die(`Could not read photos back: ${error.message}`);
const idByName = new Map(stored.map((p) => [p.file_name, p.id]));

const ids = detections.map((d) => idByName.get(d.fileName)).filter(Boolean);
for (let i = 0; i < ids.length; i += 200) {
  const { error: delErr } = await db
    .from('detections')
    .delete()
    .in('photo_id', ids.slice(i, i + 200));
  if (delErr) die(`Could not clear old detections: ${delErr.message}`);
}

const detRows = detections.flatMap((d) => {
  const photoId = idByName.get(d.fileName);
  if (!photoId) return [];
  return d.reads.map((r) => ({ ...r, photo_id: photoId }));
});

let inserted = 0;
for (let i = 0; i < detRows.length; i += 500) {
  const chunk = detRows.slice(i, i + 500);
  const { error: insErr } = await db.from('detections').insert(chunk);
  if (insErr) die(`detections insert failed at ${i}: ${insErr.message}`);
  inserted += chunk.length;
  process.stdout.write(`\r  detections: ${inserted}/${detRows.length}`);
}
if (detRows.length) process.stdout.write('\n');

log.ok(`${photos.length} photos, ${inserted} detections`);
log.info('Next: node scripts/upload-photos.mjs --dir <folder of photos>');
