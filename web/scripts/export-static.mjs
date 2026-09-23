#!/usr/bin/env node
/**
 * Publish step: write every runner's search result into the static site.
 *
 *   node scripts/export-static.mjs                 # event from NEXT_PUBLIC_EVENT_SLUG
 *   node scripts/export-static.mjs --event zeljava-2026
 *
 * Output (copied into out/ by `npm run build`):
 *   public/data/stats.json          landing-page counters
 *   public/data/bib/<bib>.json      exactly what find_runner() returns for that bib
 *
 * Why: a search then costs one CDN fetch of a ~2–5 KB file instead of a
 * database call. Cloudflare serves static assets without a request limit, so
 * the site's capacity stops depending on the Supabase instance size. The
 * database is still the source of truth and the fallback for any bib that is
 * not in the export — re-run this after every import, then rebuild + deploy.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { admin, args, DEFAULT_SLUG, die, log } from './lib.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const a = args();
const slug = a.event || DEFAULT_SLUG;
const outDir = path.resolve(__dirname, '..', 'public', 'data');
const db = admin();

log.step(`Exporting ${slug} → ${path.relative(process.cwd(), outDir)}`);

const { data: stats, error: statsErr } = await db.rpc('event_stats', { p_event_slug: slug });
if (statsErr) die(statsErr.message);
if (!stats?.ok) die(`Event "${slug}" not found or not published.`);

fs.rmSync(path.join(outDir, 'bib'), { recursive: true, force: true });
fs.mkdirSync(path.join(outDir, 'bib'), { recursive: true });

let after = '';
let runners = 0;
let photos = 0;
for (;;) {
  const { data, error } = await db.rpc('export_event', {
    p_event_slug: slug,
    p_after_bib: after,
    p_limit: 500,
  });
  if (error) die(error.message);
  if (!data?.length) break;
  for (const row of data) {
    fs.writeFileSync(path.join(outDir, 'bib', `${row.bib}.json`), JSON.stringify(row.payload));
    runners += 1;
    photos += row.payload?.photos?.length ?? 0;
  }
  after = data[data.length - 1].bib;
}

fs.writeFileSync(path.join(outDir, 'stats.json'), JSON.stringify(stats));
log.ok(`${runners} runners, ${photos} photo links, stats.json`);
log.info('Next: npm run build && npx wrangler deploy');
