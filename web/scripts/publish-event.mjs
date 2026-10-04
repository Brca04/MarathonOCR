#!/usr/bin/env node
/**
 * Put an event's current data live: check it, then rebuild the site.
 *
 *   EVENT=zagreb-2026 node scripts/publish-event.mjs            # check + rebuild
 *   EVENT=zagreb-2026 node scripts/publish-event.mjs --check    # only the check
 *
 * Imports (results, photos, bibs) change the database but not the site: the
 * site serves a snapshot (one file per bib) made during its build. This script
 * shows what the snapshot will contain, then asks Cloudflare to rebuild through
 * the Worker's deploy hook, which runs `export:static` and deploys.
 *
 * Needs SUPABASE_SERVICE_ROLE_KEY and the hook URL in web/.env.local:
 *   DEPLOY_HOOK_ZAGREB_2026=https://api.cloudflare.com/client/v4/workers/builds/deploy_hooks/…
 * (Workers & Pages → the event's Worker → Settings → Builds → Deploy Hooks.)
 */
import { admin, args, DEFAULT_SLUG, die, log } from './lib.mjs';

const a = args();
const slug = a.event || DEFAULT_SLUG;
const db = admin();

const { data: stats, error } = await db.rpc('event_stats', { p_event_slug: slug });
if (error) die(error.message);
if (!stats?.ok) die(`Event "${slug}" not found or not published.`);

log.step(`${stats.name} (${slug})`);
log.info(`runners with results   ${stats.finishers}`);
log.info(`photos                 ${stats.photos}`);
log.info(`runners with a photo   ${stats.tagged_bibs}`);

const problems = [];
if (!stats.finishers) problems.push('no results imported yet (scripts/import-results.mjs)');
if (!stats.photos) problems.push('no photos published yet (scripts/publish-photos.mjs)');
if (stats.photos && !stats.tagged_bibs) problems.push('photos have no bibs yet (scripts/import-bibs.mjs)');
problems.forEach((p) => log.warn(p));

if (a.check) process.exit(0);

const hookVar = `DEPLOY_HOOK_${slug.toUpperCase().replace(/[^A-Z0-9]/g, '_')}`;
const hook = process.env[hookVar];
if (!hook) {
  die(`Set ${hookVar} in web/.env.local (Cloudflare → the Worker → Settings → Builds → Deploy Hooks),\n` +
      '    or start the build by hand there (Deployments → latest build → Retry build).');
}
const res = await fetch(hook, { method: 'POST' });
if (!res.ok) die(`Deploy hook answered ${res.status}: ${(await res.text()).slice(0, 200)}`);
log.ok('Rebuild started. The site updates in about 2–3 minutes (Cloudflare → Deployments to watch it).');
