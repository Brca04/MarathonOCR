#!/usr/bin/env node
/**
 * Push a folder of race photos into Supabase Storage and fill in the storage
 * paths on the matching `photos` rows.
 *
 *   node scripts/upload-photos.mjs --dir "C:/photos/zagreb-2026"
 *   node scripts/upload-photos.mjs --dir ./photos --originals   # also the full files
 *   node scripts/upload-photos.mjs --dir ./photos --width 1600 --quality 78
 *
 * Two buckets, two jobs:
 *   race-previews  (public)  web-sized JPEG, optionally watermarked
 *   race-originals (private) the photographer's file, handed out only as a
 *                            short-lived signed URL
 *
 * `sharp` is used when it is installed (`npm i -D sharp`) to downscale and
 * watermark. Without it the files are uploaded untouched — fine for a prototype
 * on a small set, wasteful on 20k full-resolution frames.
 */
import fs from 'node:fs';
import path from 'node:path';
import { admin, args, DEFAULT_SLUG, die, ensureEvent, log } from './lib.mjs';

const a = args();
if (!a.dir) die('Pass --dir <folder of photos>.');
const dir = path.resolve(a.dir);
if (!fs.existsSync(dir)) die(`No such folder: ${dir}`);

const slug = a.event || DEFAULT_SLUG;
const maxWidth = Number(a.width ?? 1600);
const quality = Number(a.quality ?? 80);
const withOriginals = Boolean(a.originals);
const watermark = Boolean(a.watermark);

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.webp']);

let sharp = null;
try {
  ({ default: sharp } = await import('sharp'));
  log.info('sharp found — previews will be resized' + (watermark ? ' and watermarked' : ''));
} catch {
  log.warn('sharp not installed — uploading files unchanged (npm i -D sharp to resize)');
}

/** Width/height straight out of the file header, for when sharp is absent. */
function readDimensions(buf) {
  // PNG
  if (buf.length > 24 && buf.readUInt32BE(0) === 0x89504e47) {
    return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
  }
  // JPEG: walk the segment markers looking for a start-of-frame.
  if (buf.length > 4 && buf[0] === 0xff && buf[1] === 0xd8) {
    let i = 2;
    while (i < buf.length - 9) {
      if (buf[i] !== 0xff) {
        i++;
        continue;
      }
      const marker = buf[i + 1];
      const len = buf.readUInt16BE(i + 2);
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
        return { width: buf.readUInt16BE(i + 7), height: buf.readUInt16BE(i + 5) };
      }
      i += 2 + len;
    }
  }
  return { width: null, height: null };
}

const files = fs
  .readdirSync(dir)
  .filter((f) => IMAGE_EXTS.has(path.extname(f).toLowerCase()))
  .sort();
if (!files.length) die(`No images in ${dir}`);
log.step(`${files.length} image(s) in ${dir}`);

const db = admin();
const { event } = await ensureEvent(db, slug);

const { data: existing, error: readErr } = await db
  .from('photos')
  .select('id,file_name')
  .eq('event_id', event.id);
if (readErr) die(`Could not read photos: ${readErr.message}`);
const known = new Map((existing || []).map((p) => [p.file_name, p.id]));
log.info(`${known.size} photo row(s) already in the database for this event`);

let uploaded = 0;
let skipped = 0;
const updates = [];

for (const file of files) {
  const abs = path.join(dir, file);
  const raw = fs.readFileSync(abs);
  const base = `${slug}/${path.parse(file).name}`;

  let previewBody = raw;
  let previewType = `image/${path.extname(file).slice(1).replace('jpg', 'jpeg')}`;
  let dims = readDimensions(raw);

  if (sharp) {
    const img = sharp(raw).rotate(); // honour EXIF orientation
    const meta = await img.metadata();
    dims = { width: meta.width ?? null, height: meta.height ?? null };
    let pipeline = img.resize({ width: maxWidth, withoutEnlargement: true });
    if (watermark) {
      const w = Math.min(maxWidth, meta.width ?? maxWidth);
      const svg = Buffer.from(
        `<svg width="${w}" height="${Math.round(w * 0.08)}">
           <text x="50%" y="70%" text-anchor="middle"
                 font-family="sans-serif" font-size="${Math.round(w * 0.045)}"
                 fill="rgba(255,255,255,0.42)" letter-spacing="6">ZAGREB 2026</text>
         </svg>`,
      );
      pipeline = pipeline.composite([{ input: svg, gravity: 'south' }]);
    }
    previewBody = await pipeline.jpeg({ quality, mozjpeg: true }).toBuffer();
    previewType = 'image/jpeg';
  }

  const previewPath = `${base}.jpg`;
  const up = await db.storage
    .from('race-previews')
    .upload(previewPath, previewBody, { contentType: previewType, upsert: true });
  if (up.error) {
    log.warn(`${file}: preview upload failed — ${up.error.message}`);
    skipped++;
    continue;
  }

  let originalPath = null;
  if (withOriginals) {
    originalPath = `${base}${path.extname(file).toLowerCase()}`;
    const orig = await db.storage
      .from('race-originals')
      .upload(originalPath, raw, { contentType: previewType, upsert: true });
    if (orig.error) {
      log.warn(`${file}: original upload failed — ${orig.error.message}`);
      originalPath = null;
    }
  }

  updates.push({
    event_id: event.id,
    file_name: file,
    preview_path: previewPath,
    original_path: originalPath,
    width: dims.width,
    height: dims.height,
  });

  uploaded++;
  process.stdout.write(`\r  uploaded ${uploaded}/${files.length}`);
}
if (uploaded) process.stdout.write('\n');

// Upsert rather than update: a photo that was never in bib_export.csv (nobody's
// number was legible in it) still belongs in the gallery's storage.
for (let i = 0; i < updates.length; i += 200) {
  const { error } = await db
    .from('photos')
    .upsert(updates.slice(i, i + 200), { onConflict: 'event_id,file_name' });
  if (error) die(`photos update failed: ${error.message}`);
}

log.ok(`${uploaded} uploaded, ${skipped} skipped`);
const unmatched = files.filter((f) => !known.has(f)).length;
if (unmatched) {
  log.warn(
    `${unmatched} file(s) had no row from bib_export.csv — they are stored but nobody's ` +
      'search will surface them until a bib is read in them.',
  );
}
