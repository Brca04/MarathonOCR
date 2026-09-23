import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const EVENT_SLUG = process.env.NEXT_PUBLIC_EVENT_SLUG || 'zagreb-2026';

/**
 * Null when the environment is not configured. The app then falls back to the
 * bundled demo event, so `npm run dev` works on a fresh clone with no keys.
 */
export const supabase: SupabaseClient | null =
  url && anon
    ? createClient(url, anon, {
        auth: { persistSession: false },
        global: { headers: { 'x-app': 'zg-marathon-photos' } },
      })
    : null;

export const isLive = supabase !== null;

const PREVIEW_BUCKET = 'race-previews';

/** Public URL for a preview stored in Supabase Storage. */
export function previewUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  // Paths that already look like URLs or local assets pass straight through —
  // that is how the demo event points at /photos/*.jpg.
  if (/^(https?:|\/)/.test(path)) return path;
  if (!supabase) return null;
  return supabase.storage.from(PREVIEW_BUCKET).getPublicUrl(path).data.publicUrl;
}

/**
 * Short-lived signed URL for an original in the private bucket. Returns null
 * when it cannot be signed (demo mode, or no storage policy allows it), and the
 * download buttons then fall back to the preview.
 */
export async function signedOriginalUrl(path: string): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.storage
    .from('race-originals')
    .createSignedUrl(path, 60 * 5);
  return data?.signedUrl ?? null;
}
