#!/usr/bin/env node
/**
 * Publish an event's photos: resize, name, upload, record. Run it once the
 * photographers' folder is on this machine (re-running is safe and skips work
 * already done).
 *
 *   EVENT=zagreb-2026 node scripts/publish-photos.mjs --dir ~/Photos/ZG26
 *   EVENT=zagreb-2026 node scripts/publish-photos.mjs --dir ~/Photos/ZG26 --photographer "Ana Horvat"
 *   EVENT=zagreb-2026 node scripts/publish-photos.mjs --dir ~/Photos/ZG26 --dry-run
 *
 * For every photo (sub-folders included):
 *   1. two derivatives, rotated upright from EXIF:
 *        web  1600 px long edge  →  public/media/<event>/w/<token>.jpg
 *        thumb 520 px long edge  →  public/media/<event>/t/<token>.jpg
 *      <token> is an HMAC of the file name with MEDIA_SALT, so photo URLs cannot
 *      be guessed or counted; only a search reveals a runner's photos.
 *   2. upload of both to the R2 bucket the site serves /media/* from;
 *   3. a `photos` row with paths, size, capture time and photographer.
 * Bibs come afterwards from the review: `node scripts/import-bibs.mjs`.
 *
 * Needs in web/.env.local (never committed):
 *   SUPABASE_SERVICE_ROLE_KEY   database writes
 *   MEDIA_SALT                  any long random string; keep it forever per event,
 *                               a new salt renames every photo
 *   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
 *                               optional: fast parallel upload through R2's S3 API
 *                               (Cloudflare → R2 → Manage API tokens). Without them
 *                               it falls back to `wrangler r2 object put`, one file
 *                               at a time per worker: fine for hundreds, slow for 20k.
 * Options: --concurrency 8  --bucket <name> (default: R2_BUCKET from the event file)  --skip-upload  --skip-db
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
import { admin, args, DEFAULT_SLUG, die, ensureEvent, log, upsertBatched } from './lib.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const a = args();
const slug = a.event || DEFAULT_SLUG;
const dirArg = typeof a.dir === 'string' ? a.dir.replace(/^~(?=$|\/)/, os.homedir()) : null;
if (!dirArg) die('Pass --dir <folder of photos>.');
const dir = path.resolve(dirArg);
if (!fs.existsSync(dir)) die(`No such folder: ${dir}`);
const salt = process.env.MEDIA_SALT;
if (!salt || salt.length < 16) die('Set MEDIA_SALT (a long random string) in web/.env.local.');
const dryRun = Boolean(a['dry-run']);
const skipUpload = Boolean(a['skip-upload']);
const skipDb = Boolean(a['skip-db']);
const concurrency = Math.max(1, Number(a.concurrency || Math.min(8, os.cpus().length)));
const bucket = a.bucket || process.env.R2_BUCKET || 'marathonocr-media';
const photographer = typeof a.photographer === 'string' ? a.photographer : null;
const tz = process.env.NEXT_PUBLIC_EVENT_TZ || 'Europe/Zagreb';
const publicDir = path.resolve(__dirname, '..', 'public');

const SIZES = [
  { dir: 'w', edge: 1600, quality: 80 },
  { dir: 't', edge: 520, quality: 72 },
];
const EXTS = new Set(['.jpg', '.jpeg', '.png', '.webp', '.heic', '.tif', '.tiff']);

/** Same token the Željava load used: HMAC-SHA256("<event>/<file>")[:24]. */
export function mediaToken(eventSlug, fileName, key = salt) {
  return crypto.createHmac('sha256', key).update(`${eventSlug}/${fileName}`).digest('hex').slice(0, 24);
}

function listPhotos(root) {
  const out = [];
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name.startsWith('.')) continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (EXTS.has(path.extname(e.name).toLowerCase())) out.push(p);
    }
  };
  walk(root);
  return out.sort();
}

/** UTC offset of the race's time zone at a given wall-clock time, "+02:00". */
function tzOffset(wall) {
  const guess = new Date(wall + 'Z');
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: tz, timeZoneName: 'longOffset' }).formatToParts(guess);
  const name = parts.find((p) => p.type === 'timeZoneName')?.value || 'GMT+00:00';
  return name === 'GMT' ? '+00:00' : name.replace('GMT', '');
}

/**
 * Capture time from the EXIF block without a parser dependency: the camera
 * writes "YYYY:MM:DD HH:MM:SS" strings; DateTimeOriginal is the earliest of
 * them (a later edit only moves DateTime). An explicit OffsetTimeOriginal wins
 * over the race's time zone.
 */
function capturedAt(exif) {
  if (!exif) return null;
  const s = exif.toString('latin1');
  const stamps = [...s.matchAll(/(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/g)]
    .map((m) => `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`)
    .filter((w) => w >= '2000' && !Number.isNaN(Date.parse(w + 'Z')))
    .sort();
  if (!stamps.length) return null;
  const wall = stamps[0];
  const off = s.match(/\0([+-]\d{2}:\d{2})\0/)?.[1] ?? tzOffset(wall);
  return new Date(`${wall}${off}`).toISOString();
}

// --- upload -----------------------------------------------------------------

let s3 = null;
let PutObjectCommand = null;
if (!skipUpload && !dryRun && process.env.R2_ACCESS_KEY_ID && process.env.R2_SECRET_ACCESS_KEY && process.env.R2_ACCOUNT_ID) {
  const mod = await import('@aws-sdk/client-s3');
  PutObjectCommand = mod.PutObjectCommand;
  s3 = new mod.S3Client({
    region: 'auto',
    endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
    credentials: { accessKeyId: process.env.R2_ACCESS_KEY_ID, secretAccessKey: process.env.R2_SECRET_ACCESS_KEY },
  });
}

const run = (cmd, argv) =>
  new Promise((resolve, reject) => {
    const child = spawn(cmd, argv, { stdio: ['ignore', 'ignore', 'pipe'], shell: process.platform === 'win32' });
    let err = '';
    child.stderr.on('data', (d) => (err += d));
    child.on('close', (code) => (code === 0 ? resolve() : reject(new Error(err.trim().split('\n').pop() || `exit ${code}`))));
  });

async function upload(key, file) {
  for (let attempt = 1; ; attempt++) {
    try {
      if (s3) {
        await s3.send(new PutObjectCommand({
          Bucket: bucket, Key: key, Body: fs.readFileSync(file), ContentType: 'image/jpeg',
          CacheControl: 'public, max-age=604800',
        }));
      } else {
        await run('npx', ['wrangler', 'r2', 'object', 'put', `${bucket}/${key}`, '--file', file,
          '--content-type', 'image/jpeg', '--remote']);
      }
      return;
    } catch (e) {
      if (attempt >= 3) throw e;
      await new Promise((r) => setTimeout(r, 1000 * attempt));
    }
  }
}

// --- main -------------------------------------------------------------------

const files = listPhotos(dir);
if (!files.length) die(`No photos in ${dir}`);
// The name stored and hashed is the path inside --dir, so two photographers'
// "DSC_0001.jpg" in different sub-folders stay different photos.
const nameOf = (f) => path.relative(dir, f).split(path.sep).join('/');
const names = files.map(nameOf);
const dupes = names.filter((n, i) => names.indexOf(n) !== i);
if (dupes.length) die(`Duplicate file names: ${dupes.slice(0, 3).join(', ')}`);

log.step(`${files.length} photos for ${slug} from ${dir}`);
log.info(`upload: ${skipUpload || dryRun ? 'skipped' : s3 ? `R2 S3 API (${concurrency} at a time)` : `wrangler (${concurrency} at a time; set R2_* keys for speed)`}`);
if (dryRun) {
  for (const f of files.slice(0, 5)) log.info(`${nameOf(f)} → /media/${slug}/w/${mediaToken(slug, nameOf(f))}.jpg`);
  log.step('Dry run — nothing written.');
  process.exit(0);
}

// Keys already uploaded on an earlier run, so a re-run only sends what is new.
const manifest = path.join(publicDir, 'media', slug, '.uploaded');
fs.mkdirSync(path.dirname(manifest), { recursive: true });
const uploaded = new Set(fs.existsSync(manifest) ? fs.readFileSync(manifest, 'utf8').split('\n').filter(Boolean) : []);
const manifestOut = fs.createWriteStream(manifest, { flags: 'a' });

const rows = [];
const failed = [];
let done = 0;
const t0 = Date.now();
const queue = files.map((f, i) => ({ f, i }));

async function worker() {
  for (let job; (job = queue.shift()); ) {
    const { f } = job;
    const name = nameOf(f);
    const token = mediaToken(slug, name);
    try {
      const img = sharp(f, { failOn: 'none' });
      const meta = await img.metadata();
      // Orientations 5–8 are rotated 90°: swap so width/height match what is shown.
      const turned = (meta.orientation ?? 1) >= 5;
      const width = turned ? meta.height : meta.width;
      const height = turned ? meta.width : meta.height;
      const out = {};
      for (const s of SIZES) {
        const rel = `media/${slug}/${s.dir}/${token}.jpg`;
        const local = path.join(publicDir, rel);
        if (!fs.existsSync(local)) {
          fs.mkdirSync(path.dirname(local), { recursive: true });
          await sharp(f, { failOn: 'none' })
            .rotate()
            .resize({ width: s.edge, height: s.edge, fit: 'inside', withoutEnlargement: true })
            .jpeg({ quality: s.quality, mozjpeg: true, progressive: true })
            .toFile(local + '.part');
          fs.renameSync(local + '.part', local);
        }
        if (!skipUpload && !uploaded.has(rel)) {
          await upload(rel, local);
          uploaded.add(rel);
          manifestOut.write(rel + '\n');
        }
        out[s.dir] = '/' + rel;
      }
      rows.push({
        file_name: name,
        preview_path: out.w,
        thumb_path: out.t,
        width,
        height,
        captured_at: capturedAt(meta.exif),
        ...(photographer ? { photographer } : {}),
      });
    } catch (e) {
      failed.push(`${name}: ${e.message}`);
    }
    done++;
    if (done % 25 === 0 || done === files.length) {
      const rate = done / ((Date.now() - t0) / 1000);
      const left = Math.round((files.length - done) / Math.max(rate, 0.01));
      process.stdout.write(`\r  ${done}/${files.length}  ${rate.toFixed(1)}/s  ~${Math.ceil(left / 60)} min left   `);
    }
  }
}
await Promise.all(Array.from({ length: concurrency }, worker));
process.stdout.write('\n');
await new Promise((r) => manifestOut.end(r));

if (!skipDb && rows.length) {
  const db = admin();
  const { event } = await ensureEvent(db, slug);
  rows.sort((x, y) => x.file_name.localeCompare(y.file_name));
  await upsertBatched(db, 'photos', rows.map((r) => ({ ...r, event_id: event.id })), 'event_id,file_name');
}

log.ok(`${rows.length} photo(s) published${skipDb ? ' (database skipped)' : ''}`);
if (failed.length) {
  log.warn(`${failed.length} failed — fix and re-run, finished photos are skipped:`);
  failed.slice(0, 10).forEach((m) => log.info(`  ${m}`));
  process.exitCode = 1;
}
log.info('Next: import the reviewed bibs (scripts/import-bibs.mjs), then publish the site (scripts/publish-event.mjs).');
