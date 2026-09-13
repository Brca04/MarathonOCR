import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';

// Plain `dotenv/config` only loads a file literally named `.env`. Next.js
// itself reads `.env.local` via @next/env, but these standalone scripts
// don't get that for free — load it explicitly so `cp .env.example
// .env.local` (what the README tells you to do) actually works here too.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, '..', '.env.local') });

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

/** Parse `--key value`, `--key=value` and bare `--flag` into an object. */
export function args(argv = process.argv.slice(2)) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) {
      out._.push(a);
      continue;
    }
    const [k, inline] = a.slice(2).split('=');
    if (inline !== undefined) out[k] = inline;
    else if (argv[i + 1] && !argv[i + 1].startsWith('--')) out[k] = argv[++i];
    else out[k] = true;
  }
  return out;
}

export function die(msg) {
  console.error(`\n  ✗ ${msg}\n`);
  process.exit(1);
}

export const log = {
  step: (m) => console.log(`\n▸ ${m}`),
  info: (m) => console.log(`  ${m}`),
  warn: (m) => console.warn(`  ! ${m}`),
  ok: (m) => console.log(`  ✓ ${m}`),
};

// ---------------------------------------------------------------------------
// Supabase (service role — these scripts run on your machine, never in a build)
// ---------------------------------------------------------------------------

export function admin() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    die(
      'Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in web/.env.local\n' +
        '    (Supabase dashboard → Project Settings → API). The service role key\n' +
        '    bypasses RLS, so keep it out of git and out of the browser.',
    );
  }
  return createClient(url, key, { auth: { persistSession: false } });
}

export const DEFAULT_SLUG = process.env.NEXT_PUBLIC_EVENT_SLUG || 'zagreb-2026';

const RACE_DEFS = [
  { code: 'marathon', name: 'Marathon', distance_km: 42.195 },
  { code: 'half', name: 'Half marathon', distance_km: 21.0975 },
  { code: '10k', name: '10 km', distance_km: 10 },
];

/** Create the event and its three races if they are not there yet. */
export async function ensureEvent(db, slug, overrides = {}) {
  const { data: existing } = await db.from('events').select('*').eq('slug', slug).maybeSingle();
  let event = existing;
  if (!event) {
    const row = {
      slug,
      name: overrides.name || 'Zagrebački maraton',
      edition: overrides.edition ?? 34,
      race_date: overrides.race_date || '2026-10-11',
      city: overrides.city || 'Zagreb',
      first_year: overrides.first_year ?? 1992,
      published: true,
    };
    const { data, error } = await db.from('events').insert(row).select().single();
    if (error) die(`Could not create event: ${error.message}`);
    event = data;
    log.ok(`created event ${slug}`);
  }

  const { data: races } = await db.from('races').select('*').eq('event_id', event.id);
  const have = new Set((races || []).map((r) => r.code));
  const missing = RACE_DEFS.filter((r) => !have.has(r.code)).map((r) => ({
    ...r,
    event_id: event.id,
  }));
  if (missing.length) {
    const { error } = await db.from('races').insert(missing);
    if (error) die(`Could not create races: ${error.message}`);
    log.ok(`created races: ${missing.map((m) => m.code).join(', ')}`);
  }

  const { data: all } = await db.from('races').select('*').eq('event_id', event.id);
  const byCode = Object.fromEntries((all || []).map((r) => [r.code, r]));
  return { event, races: byCode };
}

// ---------------------------------------------------------------------------
// CSV
// ---------------------------------------------------------------------------

export function readCsv(file) {
  const abs = path.resolve(file);
  if (!fs.existsSync(abs)) die(`No such file: ${abs}`);
  // Strip a UTF-8 BOM — Excel adds one and it poisons the first header name.
  return fs.readFileSync(abs, 'utf8').replace(/^\uFEFF/, '');
}

/**
 * Header normaliser: lowercase, strip accents and anything non-alphanumeric, so
 * "Datum ro\u0111enja", "datum_rodjenja" and "DOB" can all be looked up the same way.
 *
 * NFD handles \u010d \u0107 \u017e \u0161 \u00fc \u2014 it does not touch \u0111 or \u00df, which have no decomposition,
 * so those are transliterated by hand first. Getting this wrong is silent: the
 * column simply reports as "not found".
 */
export function normHeader(h) {
  return String(h)
    .replace(/[\u0111\u0110]/g, 'd')
    .replace(/[\u00df\u1e9e]/g, 'ss')
    .replace(/[\u00f8\u00d8]/g, 'o')
    .replace(/[\u0142\u0141]/g, 'l')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
}

/**
 * Look up a logical field in a row by trying a list of header aliases.
 * Returns '' when nothing matched, so callers can treat it uniformly.
 */
export function pick(row, aliases) {
  for (const a of aliases) {
    const key = normHeader(a);
    if (row[key] !== undefined && String(row[key]).trim() !== '') return String(row[key]).trim();
  }
  return '';
}

/** Re-key a parsed record so every header is normalised. */
export function normaliseRow(record) {
  const out = {};
  for (const [k, v] of Object.entries(record)) out[normHeader(k)] = v;
  return out;
}

// ---------------------------------------------------------------------------
// Value parsing
// ---------------------------------------------------------------------------

export function digits(s, max = 6) {
  return String(s ?? '').replace(/\D/g, '').slice(0, max);
}

/**
 * Dates as they actually turn up in timing exports.
 *   1989-03-14 · 14.03.1989 · 14/03/1989 · 14-3-89 · 19890314
 * `order` is 'dmy' (European default) or 'mdy'.
 */
export function parseDate(raw, order = 'dmy') {
  const s = String(raw ?? '').trim();
  if (!s) return null;

  let m = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if (m) return iso(+m[1], +m[2], +m[3]);

  m = s.match(/^(\d{8})$/);
  if (m) return iso(+s.slice(0, 4), +s.slice(4, 6), +s.slice(6, 8));

  m = s.match(/^(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})\.?$/);
  if (m) {
    const a = +m[1];
    const b = +m[2];
    let y = +m[3];
    if (y < 100) y += y > new Date().getFullYear() % 100 ? 1900 : 2000;
    // A value over 12 can only be the day, whatever the declared order says.
    const dmy = order === 'dmy' ? a <= 31 : b > 12;
    return dmy ? iso(y, b, a) : iso(y, a, b);
  }
  return null;
}

function iso(y, mo, d) {
  if (!y || !mo || !d || mo > 12 || d > 31) return null;
  return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

/**
 * Finish times, as timing companies actually write them:
 *   "3:24:17"  "03:24:17.4"  "41:12" (mm:ss — a 10K)  "3h24m17s"  "95:12"
 *
 * A two-part value is minutes:seconds, NOT hours:minutes. That distinction
 * matters: reading a 41:12 ten-K as 41 hours is the kind of bug that survives
 * an import and only shows up as a nonsense pace on the runner's page.
 *
 * Returns a Postgres interval literal, or null.
 */
export function parseDuration(raw) {
  let s = String(raw ?? '').trim();
  if (!s || /^(dnf|dns|dsq|dq|-{1,3}|n\/?a)$/i.test(s)) return null;

  s = s.replace(/[.,]\d+\s*$/, ''); // drop fractional seconds

  const hms = s.match(/^(\d+)\s*h\s*(\d{1,2})\s*m\s*(\d{1,2})\s*s?$/i);
  if (hms) return build(+hms[1], +hms[2], +hms[3]);

  const parts = s.split(':').map((x) => x.trim());
  if (!parts.every((x) => /^\d{1,3}$/.test(x))) return null;

  if (parts.length === 3) return build(+parts[0], +parts[1], +parts[2]);
  if (parts.length === 2) return build(0, +parts[0], +parts[1]);
  return null;

  function build(h, m, sec) {
    if (sec > 59) return null;
    h += Math.floor(m / 60); // "95:12" is 1:35:12
    m %= 60;
    if (h > 99) return null;
    return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }
}

export function parseInt0(raw) {
  const n = parseInt(String(raw ?? '').replace(/[^\d-]/g, ''), 10);
  return Number.isFinite(n) ? n : null;
}

/** Map whatever the race column says onto one of our three race codes. */
export function raceCodeFrom(text, bib) {
  const t = String(text ?? '').toLowerCase();
  if (/(^|\D)(42|maraton|marathon|full)/.test(t) && !/(pol|half|1\/2)/.test(t)) return 'marathon';
  if (/(pol|half|1\/2|21)/.test(t)) return 'half';
  if (/(^|\D)(10\s*k|10k|10 km|deset)/.test(t)) return '10k';
  if (/(^|\D)(5\s*k|5k)/.test(t)) return '10k';
  // Nothing usable in the column: fall back to the bib ranges the design uses.
  const n = parseInt(bib, 10);
  if (!Number.isFinite(n)) return 'marathon';
  return n >= 5000 ? '10k' : n >= 2000 ? 'half' : 'marathon';
}

export function statusFrom(text) {
  const t = String(text ?? '').toLowerCase();
  if (/dnf/.test(t)) return 'dnf';
  if (/dns/.test(t)) return 'dns';
  if (/dsq|disq/.test(t)) return 'dsq';
  return 'finished';
}

/** Insert rows in batches so a 20k-runner CSV does not blow the request size. */
export async function upsertBatched(db, table, rows, onConflict, size = 500) {
  let done = 0;
  for (let i = 0; i < rows.length; i += size) {
    const chunk = rows.slice(i, i + size);
    const { error } = await db.from(table).upsert(chunk, { onConflict });
    if (error) die(`${table} upsert failed at row ${i}: ${error.message}`);
    done += chunk.length;
    process.stdout.write(`\r  ${table}: ${done}/${rows.length}`);
  }
  if (rows.length) process.stdout.write('\n');
  return done;
}
