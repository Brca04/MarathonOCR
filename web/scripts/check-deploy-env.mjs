/**
 * Runs before every build. On a Cloudflare build (WORKERS_CI or CF_PAGES set)
 * it refuses to build without the Supabase settings: a deployed site without
 * them cannot find anyone, and failing the build is better than shipping that.
 * Local builds only print a note.
 */
const REQUIRED = ['NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY', 'NEXT_PUBLIC_EVENT_SLUG'];
const missing = REQUIRED.filter((k) => !process.env[k]);
const onCloudflare = Boolean(process.env.WORKERS_CI || process.env.CF_PAGES);

if (missing.length && onCloudflare) {
  console.error(`\nBuild stopped: missing ${missing.join(', ')}. They come from events/zagreb-2026.env;\ncheck that scripts/event-env.mjs ran (npm run build, not next build).\n`);
  process.exit(1);
}
if (missing.length) console.log(`[env] not configured (${missing.join(', ')}): searches will find nothing.`);
else console.log(`[env] Supabase configured, event "${process.env.NEXT_PUBLIC_EVENT_SLUG}".`);
