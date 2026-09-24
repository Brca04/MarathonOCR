import { EVENT } from './event';
import type { Strings } from './i18n';

/** "3:24:17" -> 12257 */
export function toSeconds(t: string | null): number {
  if (!t) return 0;
  const parts = t.split(':').map(Number);
  if (parts.some(Number.isNaN)) return 0;
  while (parts.length < 3) parts.unshift(0);
  const [h, m, s] = parts;
  return h * 3600 + m * 60 + s;
}

/** 12257 -> "3:24:17" */
export function fromSeconds(sec: number): string {
  const t = Math.max(0, Math.round(sec));
  const h = Math.floor(t / 3600);
  const m = Math.floor(t / 60) % 60;
  const s = t % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

const EVENT_TZ = process.env.NEXT_PUBLIC_EVENT_TZ || 'Europe/Zagreb';

/**
 * Wall-clock label for a photo, e.g. "10:37" — always in the *race's* timezone,
 * not the viewer's. A runner in another country still wants to see the time it
 * was on the course.
 */
export function clockLabel(iso: string | null, fallbackMinutes = 0, startHour = 9): string {
  if (iso) {
    const d = new Date(iso);
    if (!Number.isNaN(d.getTime())) {
      try {
        return new Intl.DateTimeFormat('en-GB', {
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
          timeZone: EVENT_TZ,
        }).format(d);
      } catch {
        return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      }
    }
  }
  const h = startHour + Math.floor(fallbackMinutes / 60);
  return `${String(h).padStart(2, '0')}:${String(fallbackMinutes % 60).padStart(2, '0')}`;
}

export const easeOutCubic = (x: number) => 1 - Math.pow(1 - x, 3);
export const easeOutQuart = (x: number) => 1 - Math.pow(1 - x, 4);

/** Course markers for the progress track under the runner hero. */
export function trackMarks(raceCode: string, t: Strings) {
  const positions =
    raceCode === 'marathon'
      ? ['0%', '23.7%', '50%', '71.1%', '100%']
      : raceCode === 'half'
        ? ['0%', '23.7%', '47.4%', '71.1%', '100%']
        : raceCode === '10k'
          ? ['0%', '25%', '50%', '75%', '100%']
          : ['0%', '100%'];
  const marks: [string, string][] = t
    .trackMarks(raceCode)
    .map((label, i) => [label, positions[i]] as [string, string]);
  return marks.map(([label, left], i, a) => ({
    label,
    left,
    shift: i === 0 ? '0' : i === a.length - 1 ? '-100%' : '-50%',
    align: (i === 0 ? 'start' : i === a.length - 1 ? 'end' : 'center') as 'start' | 'end' | 'center',
  }));
}

export function raceFromBib(bib: string, t: Strings): { label: string; name: string } {
  // Events with several distances and no bib ranges say so on the card instead
  // of guessing (NEXT_PUBLIC_EVENT_RACE_BADGE / _LABEL).
  if (EVENT.raceBadge) return { label: EVENT.raceBadge, name: EVENT.raceLabel };
  const n = parseInt(bib, 10);
  const km = EVENT.raceKm
    ? Math.round(EVENT.raceKm)
    : !bib ? 42 : n >= 5000 ? 10 : n >= 2000 ? 21 : 42;
  return {
    label: `${km}K`,
    name: km === 42 ? t.raceMarathon : km === 21 ? t.raceHalf : t.race10k,
  };
}

