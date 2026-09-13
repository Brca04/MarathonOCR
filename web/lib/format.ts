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

/** "14031989" -> "14 · 03 · 1989" */
export function formatDobInput(digits: string): string {
  const d = digits.replace(/\D/g, '').slice(0, 8);
  return [d.slice(0, 2), d.slice(2, 4), d.slice(4, 8)].filter(Boolean).join(' · ');
}

/** "14 · 03 · 1989" -> "1989-03-14", or null while incomplete/invalid. */
export function dobToIso(text: string): string | null {
  const d = text.replace(/\D/g, '');
  if (d.length !== 8) return null;
  const day = Number(d.slice(0, 2));
  const month = Number(d.slice(2, 4));
  const year = Number(d.slice(4, 8));
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  if (year < 1900 || year > new Date().getFullYear()) return null;
  const iso = `${d.slice(4, 8)}-${d.slice(2, 4)}-${d.slice(0, 2)}`;
  const probe = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(probe.getTime()) || probe.getUTCDate() !== day) return null;
  return iso;
}

/** Course markers for the progress track under the runner hero. */
export function trackMarks(raceCode: string) {
  const marks: [string, string][] =
    raceCode === 'marathon'
      ? [['Start', '0%'], ['10K', '23.7%'], ['Half', '50%'], ['30K', '71.1%'], ['Finish 42.195', '100%']]
      : raceCode === 'half'
        ? [['Start', '0%'], ['5K', '23.7%'], ['10K', '47.4%'], ['15K', '71.1%'], ['Finish 21.1', '100%']]
        : [['Start', '0%'], ['2.5K', '25%'], ['5K', '50%'], ['7.5K', '75%'], ['Finish 10', '100%']];
  return marks.map(([label, left], i, a) => ({
    label,
    left,
    shift: i === 0 ? '0' : i === a.length - 1 ? '-100%' : '-50%',
    align: (i === 0 ? 'start' : i === a.length - 1 ? 'end' : 'center') as 'start' | 'end' | 'center',
  }));
}

export function raceFromBib(bib: string): { label: string; name: string } {
  const n = parseInt(bib, 10);
  const km = !bib ? 42 : n >= 5000 ? 10 : n >= 2000 ? 21 : 42;
  return {
    label: `${km}K`,
    name:
      km === 42 ? 'Marathon · 42.195 km' : km === 21 ? 'Half marathon · 21.1 km' : 'Run · 10 km',
  };
}
