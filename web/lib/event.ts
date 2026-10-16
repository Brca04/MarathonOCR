/**
 * Everything that makes the site *this* race rather than any race. Read from
 * build-time env so one codebase can be deployed per event; the defaults are
 * the Zagreb Marathon, which is what the design file was drawn for.
 *
 * Leave a value empty (e.g. NEXT_PUBLIC_EVENT_EDITION=) to hide it, or set it
 * to "none" where the host drops empty variables (Cloudflare build settings do).
 */
const env = (v: string | undefined, fallback: string) => {
  if (v === undefined) return fallback;
  const t = v.trim();
  return t.toLowerCase() === 'none' ? '' : t;
};

const list = (v: string) => v.split(',').map((x) => x.trim()).filter(Boolean);

const edition = env(process.env.NEXT_PUBLIC_EVENT_EDITION, '34');
const raceKm = env(process.env.NEXT_PUBLIC_EVENT_RACE_KM, '');

export const EVENT = {
  /** Croatian name, without the edition: "Zagrebački maraton". */
  name: env(process.env.NEXT_PUBLIC_EVENT_NAME, 'Zagrebački maraton'),
  /** English name: "Zagreb Marathon". */
  nameEn: env(process.env.NEXT_PUBLIC_EVENT_NAME_EN, 'Zagreb Marathon'),
  /** The word of the name set in the accent colour on the hero. */
  accent: env(process.env.NEXT_PUBLIC_EVENT_ACCENT, 'Zagrebački'),
  edition: edition ? Number(edition) : null,
  city: env(process.env.NEXT_PUBLIC_EVENT_CITY, 'Zagreb'),
  /** ISO date of the race, "2026-10-11". */
  date: env(process.env.NEXT_PUBLIC_EVENT_DATE, '2026-10-11'),
  /** Set for a single-distance event, e.g. 21.0975; empty = guess from bib ranges. */
  raceKm: raceKm ? Number(raceKm) : null,
  /** Hero photo, or two comma-separated: the first for desktop, the second for phones. */
  heroImages: list(env(process.env.NEXT_PUBLIC_HERO_IMAGE, '/brand/zagreb-hero-1.jpg,/brand/zagreb-hero-2.jpg')),
  /** Card text for multi-distance events, e.g. "3 UTRKE" / "21,1 km · 10 km · 3,5 km". */
  raceBadge: env(process.env.NEXT_PUBLIC_EVENT_RACE_BADGE, ''),
  raceLabel: env(process.env.NEXT_PUBLIC_EVENT_RACE_LABEL, ''),
  /** Colour scheme, matched by `:root[data-event='…']` in globals.css. Empty = the default blue. */
  theme: env(process.env.NEXT_PUBLIC_EVENT_THEME, ''),
  /** Where each hero photo is anchored when cropped (CSS object-position), in the same order. */
  heroPositions: list(env(process.env.NEXT_PUBLIC_HERO_POSITION, 'center 30%')),
  /** Photographer of the hero photos, shown small on them: "Foto: Krume Ivanovski". */
  heroCredit: env(process.env.NEXT_PUBLIC_HERO_CREDIT, ''),
  /** Fixed text for the photo counter on the hero ("10k+"); empty = the live count. */
  statPhotos: env(process.env.NEXT_PUBLIC_STAT_PHOTOS, ''),
  /** Public address of this deployment, for link previews: "https://bibfind.eu". */
  siteUrl: env(process.env.NEXT_PUBLIC_SITE_URL, ''),
  /** 1200 x 630 picture for link previews (WhatsApp, Facebook). */
  ogImage: env(process.env.NEXT_PUBLIC_OG_IMAGE, ''),
};

/**
 * True until race day is over (in the race's own time zone, roughly): the site
 * then says photos come after the race instead of offering a search that can
 * only fail. Publishing photos for the event also ends it (see page.tsx).
 */
export function beforeRace(now: Date = new Date()): boolean {
  const end = new Date(EVENT.date + 'T23:59:59');
  return !Number.isNaN(end.getTime()) && now.getTime() < end.getTime();
}

/** The first hero photo and its crop: the fallback picture elsewhere on the site. */
export const HERO_IMAGE = EVENT.heroImages[0] || '';
export const heroPosition = (i: number) => EVENT.heroPositions[i] || EVENT.heroPositions[0] || 'center 30%';

export const EVENT_YEAR = Number(EVENT.date.slice(0, 4)) || new Date().getFullYear();

/** "34. Zagrebački maraton" / "34th Zagreb Marathon" / plain name without an edition. */
export function eventTitle(lang: 'hr' | 'en'): string {
  const name = lang === 'hr' ? EVENT.name : EVENT.nameEn;
  if (EVENT.edition == null) return name;
  if (lang === 'hr') return `${EVENT.edition}. ${name}`;
  const n = EVENT.edition;
  const sfx = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${sfx} ${name}`;
}

/** "11. listopada 2026." / "11 October 2026". */
export function eventDateLabel(lang: 'hr' | 'en'): string {
  const d = new Date(EVENT.date + 'T12:00:00');
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(lang === 'hr' ? 'hr-HR' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}
