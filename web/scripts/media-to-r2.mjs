#!/usr/bin/env node
/**
 * Copy an event's photo files into the R2 bucket the guard Worker serves
 * /media/* from (binding MEDIA in wrangler.jsonc).
 *
 *   npm run media:r2                                  # event from NEXT_PUBLIC_EVENT_SLUG
 *   npm run media:r2 -- --event zeljava-2026
 *   npm run media:r2 -- --from https://marathonocr.bruno-cavor.workers.dev
 *
 * Each photo's preview_path and thumb_path ("/media/<event>/w/<id>.jpg") become
 * the R2 key without the leading slash, so the paths in Supabase stay as they
 * are. A file is taken from web/public/media/ when it is there; otherwise it is
 * downloaded from --from (the live site), which is how a machine that never
 * built the media can still fill the bucket.
 *
 * Uploads go through `wrangler r2 object put --remote`, so run
 * `npx wrangler login` once first. Re-running is safe: it overwrites.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { admin, args, DEFAULT_SLUG, die, log } from './lib.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const a = args();
const slug = a.event || DEFAULT_SLUG;
const bucket = a.bucket || 'marathonocr-media';
const from = typeof a.from === 'string' ? a.from.replace(/\/$/, '') : null;
const concurrency = Number(a.concurrency || 8);
const publicDir = path.resolve(__dirname, '..', 'public');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'media-r2-'));
const db = admin();

const { data: event, error: evErr } = await db.from('events').select('id').eq('slug', slug).maybeSingle();
if (evErr) die(evErr.message);
if (!event) die(`Event "${slug}" not found.`);

const paths = new Set();
for (let offset = 0; ; offset += 1000) {
  const { data, error } = await db
    .from('photos')
    .select('preview_path, thumb_path')
    .eq('event_id', event.id)
    .range(offset, offset + 999);
  if (error) die(error.message);
  for (const r of data) {
    for (const p of [r.preview_path, r.thumb_path]) if (p?.startsWith('/media/')) paths.add(p);
  }
  if (data.length < 1000) break;
}

log.step(`${paths.size} files for ${slug} → r2://${bucket}`);

const run = (cmd, argv) =>
  new Promise((resolve, reject) => {
    const child = spawn(cmd, argv, { stdio: ['ignore', 'ignore', 'pipe'], shell: process.platform === 'win32' });
    let err = '';
    child.stderr.on('data', (d) => (err += d));
    child.on('close', (code) => (code === 0 ? resolve() : reject(new Error(err.trim().split('\n').pop()))));
  });

async function localOrDownload(p) {
  const local = path.join(publicDir, p);
  if (fs.existsSync(local)) return local;
  if (!from) throw new Error(`not in public/ and no --from given`);
  const res = await fetch(from + p);
  if (!res.ok) throw new Error(`download ${res.status}`);
  const file = path.join(tmp, p.replace(/[\\/]/g, '_'));
  fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
  return file;
}

const queue = [...paths];
let done = 0;
const failed = [];
async function worker() {
  for (let p; (p = queue.shift()); ) {
    try {
      const file = await localOrDownload(p);
      await run('npx', ['wrangler', 'r2', 'object', 'put', `${bucket}/${p.slice(1)}`,
        '--file', file, '--content-type', 'image/jpeg', '--remote']);
    } catch (e) {
      failed.push(`${p}: ${e.message}`);
    }
    done += 1;
    if (done % 50 === 0 || done === paths.size) log.info(`${done}/${paths.size}`);
  }
}
await Promise.all(Array.from({ length: concurrency }, worker));
fs.rmSync(tmp, { recursive: true, force: true });

if (failed.length) {
  failed.slice(0, 20).forEach((f) => log.warn(f));
  die(`${failed.length} of ${paths.size} files failed — fix and re-run.`);
}
log.ok(`${paths.size} files in r2://${bucket}`);
