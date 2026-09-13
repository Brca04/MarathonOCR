/**
 * Runs before every build. On Cloudflare Pages (CF_PAGES=1) it refuses to build
 * without Supabase credentials, because the app falls back to the bundled demo
 * event when they are missing — and a deployed site quietly serving three
 * invented runners as if they were real results is worse than a failed build.
 *
 * Local builds are unaffected: no CF_PAGES, no check. For a deliberate
 * demo-data deployment — a throwaway test site before Supabase exists — set
 * ALLOW_DEMO_BUILD=1 in the Pages environment variables.
 */
const REQUIRED = ['NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY', 'NEXT_PUBLIC_EVENT_SLUG'];

if (!process.env.CF_PAGES) {
  const missing = REQUIRED.filter((k) => !process.env[k]);
  if (missing.length) {
    console.log(`[env] not configured (${missing.join(', ')}) — building against the demo event.`);
  }
  process.exit(0);
}

const missing = REQUIRED.filter((k) => !process.env[k]);

if (missing.length && process.env.ALLOW_DEMO_BUILD === '1') {
  console.warn(
    [
      '',
      '[env] ALLOW_DEMO_BUILD=1 — building WITHOUT Supabase.',
      '      This deployment will serve the bundled demo runners (Ivana Horvat',
      '      and friends). Do not point a real domain at it, and remove the',
      '      variable once the project has credentials.',
      '',
    ].join('\n'),
  );
  process.exit(0);
}

if (missing.length) {
  console.error(
    [
      '',
      'Build stopped: this deployment has no Supabase configuration.',
      '',
      `  missing: ${missing.join(', ')}`,
      '',
      'Without it the site serves the bundled demo runners as if they were real',
      'results. Set these in the Cloudflare Pages project under Settings →',
      'Environment variables, for BOTH Production and Preview, then redeploy.',
      '',
      'Deliberately deploying the demo (a throwaway test site)? Set',
      'ALLOW_DEMO_BUILD=1 alongside them.',
      '',
    ].join('\n'),
  );
  process.exit(1);
}

console.log(`[env] Supabase configured, event "${process.env.NEXT_PUBLIC_EVENT_SLUG}".`);
