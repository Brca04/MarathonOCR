import { EVENT_SLUG, isLive, previewUrl, supabase } from './supabase';
import { DEMO_STATS, demoFind } from './demo';
import { clockLabel } from './format';
import type { EventStats, FindRunnerResult, GalleryPhoto, PhotoMatch } from './types';

/**
 * Static data published next to the site by scripts/export-static.mjs: one
 * JSON file per bib plus the landing-page counters. When it is there, a search
 * is a single CDN fetch and never touches the database — that is what carries
 * race-day traffic. Supabase stays as the fallback for anything not exported.
 */
const STATIC_BASE = process.env.NEXT_PUBLIC_STATIC_DATA ?? '/data';

async function fetchStatic<T>(path: string): Promise<T | 'missing' | null> {
  if (!STATIC_BASE) return null;
  try {
    const res = await fetch(`${STATIC_BASE}/${path}`, { cache: 'default' });
    if (res.status === 404) return 'missing';
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // offline or blocked: let the caller try the database
  }
}

/** Landing-page counters. Falls back to the demo event when unconfigured. */
export async function getEventStats(): Promise<EventStats> {
  const cached = await fetchStatic<EventStats>('stats.json');
  if (cached && cached !== 'missing' && cached.ok) return cached;
  if (!supabase) return DEMO_STATS;
  const { data, error } = await supabase.rpc('event_stats', { p_event_slug: EVENT_SLUG });
  if (error || !data || !(data as EventStats).ok) {
    if (error) console.warn('[event_stats]', error.message);
    return DEMO_STATS;
  }
  return data as EventStats;
}

/**
 * The bib lookup. Birthdate verification is switched off for now, so the bib
 * alone opens a gallery; find_runner() treats a null p_dob as "skip the check".
 */
export async function findRunner(bib: string): Promise<FindRunnerResult> {
  const clean = bib.replace(/\D/g, '');
  if (!clean) return { ok: false, reason: 'missing_input' };

  const cached = await fetchStatic<FindRunnerResult>(`bib/${clean}.json`);
  if (cached && cached !== 'missing') return cached;
  // The export covers every runner, so a 404 is a real "no such bib" — unless
  // the index says otherwise (no export yet), in which case ask the database.
  if (cached === 'missing' && (await hasStaticIndex())) return { ok: false, reason: 'no_bib' };

  if (!supabase) return demoFind(bib);
  const { data, error } = await supabase.rpc('find_runner', {
    p_event_slug: EVENT_SLUG,
    p_bib: clean,
    p_dob: null,
  });
  if (error) {
    console.warn('[find_runner]', error.message);
    return { ok: false, reason: 'no_event' };
  }
  return data as FindRunnerResult;
}

let indexProbe: Promise<boolean> | null = null;
function hasStaticIndex(): Promise<boolean> {
  indexProbe ??= fetchStatic<{ ok: boolean }>('stats.json').then((r) => Boolean(r && r !== 'missing' && r.ok));
  return indexProbe;
}

/** Resolve storage paths to URLs and add the labels the gallery renders. */
export function toGallery(photos: PhotoMatch[]): GalleryPhoto[] {
  return photos.map((p, i) => {
    const w = p.width ?? 3;
    const h = p.height ?? 2;
    return {
      ...p,
      src: previewUrl(p.preview_path) ?? '/photos/zg-44.jpg',
      thumb: previewUrl(p.thumb_path) ?? previewUrl(p.preview_path) ?? '/photos/zg-44.jpg',
      clock: clockLabel(p.captured_at, i * 20),
      hint: [p.course_point, p.photographer].filter(Boolean).join(' · ') || 'Race photo',
      dims: p.width && p.height ? `${p.width} × ${p.height} px` : '—',
      ratio: `${w}/${h}`,
    };
  });
}

export { isLive, EVENT_SLUG };
