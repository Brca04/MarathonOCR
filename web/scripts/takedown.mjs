#!/usr/bin/env node
/**
 * Take something off the site after a removal request.
 *
 *   EVENT=zagreb-2026 node scripts/takedown.mjs --photo "Cilj/DSC_0412.jpg"   # one photo, for everyone
 *   EVENT=zagreb-2026 node scripts/takedown.mjs --bib 1042                    # a runner: their page and photo links
 *   … add --dry-run to see what would change.
 *
 * --photo deletes the photo, its bib reads and both image files from R2.
 * --bib deletes the runner's result row and every bib read of that number, so
 *   searching it finds nothing; the photos stay for the other runners in them.
 * Then run scripts/publish-event.mjs so the rebuilt site drops it too. Keep a
 * note of the request (who, when, what) for your GDPR records.
 */
import { spawn } from 'node:child_process';
import { admin, args, DEFAULT_SLUG, die, log } from './lib.mjs';

const a = args();
const slug = a.event || DEFAULT_SLUG;
const dryRun = Boolean(a['dry-run']);
if (!a.photo && !a.bib) die('Pass --photo <file name> or --bib <number>.');
const db = admin();
const { data: event } = await db.from('events').select('id').eq('slug', slug).maybeSingle();
if (!event) die(`Event "${slug}" not found.`);

async function deleteR2(key) {
  if (process.env.R2_ACCESS_KEY_ID && process.env.R2_SECRET_ACCESS_KEY && process.env.R2_ACCOUNT_ID) {
    const { S3Client, DeleteObjectCommand } = await import('@aws-sdk/client-s3');
    const s3 = new S3Client({
      region: 'auto',
      endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
      credentials: { accessKeyId: process.env.R2_ACCESS_KEY_ID, secretAccessKey: process.env.R2_SECRET_ACCESS_KEY },
    });
    await s3.send(new DeleteObjectCommand({ Bucket: a.bucket || 'marathonocr-media', Key: key }));
    return;
  }
  await new Promise((resolve, reject) => {
    const c = spawn('npx', ['wrangler', 'r2', 'object', 'delete', `${a.bucket || 'marathonocr-media'}/${key}`, '--remote'], { stdio: 'inherit' });
    c.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`wrangler exit ${code}`))));
  });
}

if (a.photo) {
  const { data: photo } = await db.from('photos').select('id,file_name,preview_path,thumb_path')
    .eq('event_id', event.id).eq('file_name', String(a.photo)).maybeSingle();
  if (!photo) die(`No photo "${a.photo}" in ${slug}.`);
  log.step(`Photo ${photo.file_name}`);
  if (dryRun) {
    log.info(`would delete the row, its bib reads and ${photo.preview_path}, ${photo.thumb_path}`);
    process.exit(0);
  }
  await db.from('detections').delete().eq('photo_id', photo.id);
  const { error } = await db.from('photos').delete().eq('id', photo.id);
  if (error) die(error.message);
  for (const p of [photo.preview_path, photo.thumb_path]) if (p?.startsWith('/media/')) await deleteR2(p.slice(1));
  log.ok('removed');
}

if (a.bib) {
  const bib = String(a.bib).replace(/\D/g, '');
  const { data: photoIds } = await db.from('photos').select('id').eq('event_id', event.id);
  const ids = (photoIds || []).map((p) => p.id);
  const { count: reads } = await db.from('detections').select('id', { count: 'exact', head: true })
    .in('photo_id', ids.length ? ids : ['00000000-0000-0000-0000-000000000000']).eq('bib_text', bib);
  const { data: runner } = await db.from('runners').select('id,full_name').eq('event_id', event.id).eq('bib', bib).maybeSingle();
  log.step(`Bib ${bib}${runner ? ` (${runner.full_name})` : ''}: ${reads ?? 0} photo read(s)`);
  if (dryRun) process.exit(0);
  for (let i = 0; i < ids.length; i += 500) {
    await db.from('detections').delete().in('photo_id', ids.slice(i, i + 500)).eq('bib_text', bib);
  }
  if (runner) await db.from('runners').delete().eq('id', runner.id);
  log.ok('removed');
}
log.info('Next: node scripts/publish-event.mjs to rebuild the site without it.');
