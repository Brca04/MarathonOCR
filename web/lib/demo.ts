import type { EventStats, FindRunnerResult, PhotoMatch, Runner } from './types';

/**
 * The bundled demo event. It exists so a fresh clone runs with no keys at all:
 * `npm install && npm run dev` gives you the full three-screen flow. As soon as
 * NEXT_PUBLIC_SUPABASE_URL is set, every one of these functions is bypassed and
 * the same shapes come out of Postgres instead.
 *
 * The three runners and the course points are the ones from the design file.
 */

export const DEMO_STATS: EventStats = {
  ok: true,
  name: 'Zagrebački maraton',
  edition: 34,
  race_date: '2026-10-11',
  city: 'Zagreb',
  first_year: 1992,
  finishers: 6214,
  photos: 11,
  tagged_bibs: 3,
  distance_km: 42.195,
  course_record: '2:09:55',
};

type DemoRunner = Runner & { dob: string };

export const DEMO_RUNNERS: DemoRunner[] = [
  {
    bib: '1042',
    dob: '1989-03-14',
    name: 'Ivana Horvat',
    category: 'W35',
    club: 'AK Maraton 2000',
    nationality: 'HRV',
    race: 'Marathon',
    race_code: 'marathon',
    distance_km: 42.195,
    status: 'finished',
    time: '3:24:17',
    pace: '4:51',
    place_overall: 212,
    place_category: 14,
  },
  {
    bib: '2318',
    dob: '1994-07-02',
    name: 'Marko Kovačević',
    category: 'M30',
    club: 'Zagreb Runners',
    nationality: 'HRV',
    race: 'Half marathon',
    race_code: 'half',
    distance_km: 21.0975,
    status: 'finished',
    time: '1:31:05',
    pace: '4:19',
    place_overall: 148,
    place_category: 31,
  },
  {
    bib: '5077',
    dob: '1977-11-23',
    name: 'Lukas Weber',
    category: 'M45',
    club: 'LG Graz',
    nationality: 'AUT',
    race: 'Marathon',
    race_code: 'marathon',
    distance_km: 42.195,
    status: 'finished',
    time: '3:02:48',
    pace: '4:20',
    place_overall: 86,
    place_category: 7,
  },
];

const DEMO_FILES = [
  '/photos/zg-44.jpg',
  '/photos/zg-hero.jpg',
  '/photos/zg-48.jpg',
  '/photos/zg-47.jpg',
  '/photos/zg-41.jpg',
  '/photos/zg-runner.jpg',
];

const PHOTOGRAPHERS = ['Ana Perić', 'Dario Šimić', 'Mia Novak', 'Petar Jurić'];

const POINTS: { point: string; km: number; minutes: number; hint: string }[] = [
  { point: 'Start', km: 0, minutes: 0, hint: 'Start on Trg bana Jelačića' },
  { point: '5K', km: 5, minutes: 24, hint: 'Lead pack on Ilica' },
  { point: '10K', km: 10, minutes: 49, hint: 'Runner mid-stride' },
  { point: '10K', km: 10.2, minutes: 51, hint: 'Cheering zone' },
  { point: 'Half', km: 21.1, minutes: 103, hint: 'Maksimirska' },
  { point: 'Half', km: 21.4, minutes: 104, hint: 'Water station' },
  { point: '30K', km: 30, minutes: 148, hint: 'Vlaška' },
  { point: '35K', km: 35, minutes: 173, hint: 'Km 35' },
  { point: 'Finish', km: 42.1, minutes: 204, hint: 'Sprint to the finish' },
  { point: 'Finish', km: 42.195, minutes: 204, hint: 'Finish line, arms up' },
  { point: 'Finish', km: 42.2, minutes: 210, hint: 'Medal portrait' },
];

function isoAt(minutes: number): string {
  const start = new Date('2026-10-11T09:00:00+02:00').getTime();
  return new Date(start + minutes * 60_000).toISOString();
}

export function demoPhotos(bib: string): PhotoMatch[] {
  const seed = parseInt(bib, 10) || 0;
  return POINTS.map((p, i) => ({
    id: `${bib}-${i}`,
    file_name: `ZG26_${String(1000 + seed + i)}.jpg`,
    preview_path: DEMO_FILES[(seed + i) % DEMO_FILES.length],
    original_path: null,
    width: 6000,
    height: 4000,
    captured_at: isoAt(p.minutes),
    photographer: PHOTOGRAPHERS[(seed + i) % PHOTOGRAPHERS.length],
    course_point: p.point,
    course_km: p.km,
    // One deliberately fuzzy hit per gallery: the recognizer dropped a leading
    // digit, the trigram search caught it anyway, and the UI has to say so.
    match_kind: i === 6 ? 'fuzzy' : 'exact',
    match_score: i === 6 ? 0.51 : 0.93,
    read_as: i === 6 ? bib.slice(1) : bib,
  }));
}

export function demoFind(bib: string, dobIso: string): FindRunnerResult {
  const digits = bib.replace(/\D/g, '');
  if (!digits || !dobIso) return { ok: false, reason: 'missing_input' };
  const r = DEMO_RUNNERS.find((x) => x.bib === digits);
  if (!r) return { ok: false, reason: 'no_bib' };
  if (r.dob !== dobIso) return { ok: false, reason: 'dob_mismatch' };
  const { dob: _dob, ...runner } = r;
  return { ok: true, runner, photos: demoPhotos(r.bib) };
}
