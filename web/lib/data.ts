import { EVENT_SLUG, isLive, previewUrl, supabase } from './supabase';
import { DEMO_STATS, demoFind } from './demo';
import { clockLabel } from './format';
import type { EventStats, FindRunnerResult, GalleryPhoto, PhotoMatch } from './types';

/** Landing-page counters. Falls back to the demo event when unconfigured. */
export async function getEventStats(): Promise<EventStats> {
  if (!supabase) return DEMO_STATS;
  const { data, error } = await supabase.rpc('event_stats', { p_event_slug: EVENT_SLUG });
  if (error || !data || !(data as EventStats).ok) {
    if (error) console.warn('[event_stats]', error.message);
    return DEMO_STATS;
  }
  return data as EventStats;
}

/**
 * The bib + birthdate lookup. Note that nothing here can enumerate runners:
 * find_runner() is the only reachable entry point and it needs both halves.
 */
export async function findRunner(bib: string, dobIso: string): Promise<FindRunnerResult> {
  if (!supabase) return demoFind(bib, dobIso);
  const { data, error } = await supabase.rpc('find_runner', {
    p_event_slug: EVENT_SLUG,
    p_bib: bib,
    p_dob: dobIso,
  });
  if (error) {
    console.warn('[find_runner]', error.message);
    return { ok: false, reason: 'no_event' };
  }
  return data as FindRunnerResult;
}

/** Fire-and-forget purchase log. Silent on failure — it must never block a UI. */
export async function recordOrder(
  bib: string,
  kind: 'single' | 'bundle',
  photoId: string | null,
  amountEur: number,
): Promise<void> {
  if (!supabase) return;
  await supabase
    .rpc('record_order', {
      p_event_slug: EVENT_SLUG,
      p_bib: bib,
      p_kind: kind,
      p_photo_id: photoId,
      p_amount: amountEur,
    })
    .then(undefined, () => undefined);
}

/** Resolve storage paths to URLs and add the labels the gallery renders. */
export function toGallery(photos: PhotoMatch[]): GalleryPhoto[] {
  return photos.map((p, i) => {
    const w = p.width ?? 3;
    const h = p.height ?? 2;
    return {
      ...p,
      src: previewUrl(p.preview_path) ?? '/photos/zg-44.jpg',
      clock: clockLabel(p.captured_at, i * 20),
      hint: [p.course_point, p.photographer].filter(Boolean).join(' · ') || 'Race photo',
      dims: p.width && p.height ? `${p.width} × ${p.height} px` : '—',
      ratio: `${w}/${h}`,
    };
  });
}

export { isLive, EVENT_SLUG };
