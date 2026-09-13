#!/usr/bin/env node
/**
 * Put the demo event into a real Supabase project, so you can prove the live
 * path (RLS, find_runner, fuzzy matching) before your own data is ready.
 *
 *   node scripts/seed-demo.mjs
 *   node scripts/seed-demo.mjs --event zagreb-demo
 *
 * Preview paths point at the bundled /photos/*.jpg, so nothing is uploaded.
 */
import { admin, args, DEFAULT_SLUG, ensureEvent, log, upsertBatched } from './lib.mjs';

const a = args();
const slug = a.event || DEFAULT_SLUG;

const RUNNERS = [
  { bib: '1042', dob: '1989-03-14', full_name: 'Ivana Horvat', gender: 'F', category: 'W35',
    club: 'AK Maraton 2000', nationality: 'HRV', race: 'marathon', finish_time: '3:24:17',
    place_overall: 212, place_category: 14 },
  { bib: '2318', dob: '1994-07-02', full_name: 'Marko Kovačević', gender: 'M', category: 'M30',
    club: 'Zagreb Runners', nationality: 'HRV', race: 'half', finish_time: '1:31:05',
    place_overall: 148, place_category: 31 },
  { bib: '5077', dob: '1977-11-23', full_name: 'Lukas Weber', gender: 'M', category: 'M45',
    club: 'LG Graz', nationality: 'AUT', race: 'marathon', finish_time: '3:02:48',
    place_overall: 86, place_category: 7 },
  // A course-record holder so the landing page counter has something to roll to.
  { bib: '1', dob: '1996-01-09', full_name: 'Tadesse Bekele', gender: 'M', category: 'M20',
    club: 'Elite', nationality: 'ETH', race: 'marathon', finish_time: '2:09:55',
    place_overall: 1, place_category: 1 },
];

const FILES = [
  '/photos/zg-44.jpg',
  '/photos/zg-hero.jpg',
  '/photos/zg-48.jpg',
  '/photos/zg-47.jpg',
  '/photos/zg-41.jpg',
  '/photos/zg-runner.jpg',
];
const PHOTOGRAPHERS = ['Ana Perić', 'Dario Šimić', 'Mia Novak', 'Petar Jurić'];
const POINTS = [
  ['Start', 0, 0], ['5K', 5, 24], ['10K', 10, 49], ['10K', 10.2, 51],
  ['Half', 21.1, 103], ['Half', 21.4, 104], ['30K', 30, 148], ['35K', 35, 173],
  ['Finish', 42.1, 204], ['Finish', 42.195, 204], ['Finish', 42.2, 210],
];

const START = new Date('2026-10-11T09:00:00+02:00').getTime();

const db = admin();
const { event, races } = await ensureEvent(db, slug);

log.step(`Seeding demo data into ${slug}`);

await upsertBatched(
  db,
  'runners',
  RUNNERS.map(({ race, ...r }) => ({ ...r, event_id: event.id, race_id: races[race].id })),
  'event_id,bib',
);

const photos = [];
for (const runner of RUNNERS.slice(0, 3)) {
  const seed = parseInt(runner.bib, 10);
  POINTS.forEach(([point, km, minutes], i) => {
    photos.push({
      event_id: event.id,
      file_name: `ZG26_${runner.bib}_${String(i).padStart(2, '0')}.jpg`,
      preview_path: FILES[(seed + i) % FILES.length],
      width: 6000,
      height: 4000,
      captured_at: new Date(START + minutes * 60_000).toISOString(),
      photographer: PHOTOGRAPHERS[(seed + i) % PHOTOGRAPHERS.length],
      course_point: point,
      course_km: km,
      _bib: runner.bib,
      _i: i,
    });
  });
}

await upsertBatched(
  db,
  'photos',
  photos.map(({ _bib, _i, ...p }) => p),
  'event_id,file_name',
);

const { data: stored } = await db.from('photos').select('id,file_name').eq('event_id', event.id);
const idByName = new Map((stored || []).map((p) => [p.file_name, p.id]));

const ids = photos.map((p) => idByName.get(p.file_name)).filter(Boolean);
for (let i = 0; i < ids.length; i += 200) {
  await db.from('detections').delete().in('photo_id', ids.slice(i, i + 200));
}

const detections = photos.flatMap((p) => {
  const photo_id = idByName.get(p.file_name);
  if (!photo_id) return [];
  // Photo 7 of each set carries a truncated read — the leading digit was lost.
  // Only the edit-distance-1 tier finds it, which is the point of seeding it.
  const truncated = p._i === 6;
  return [
    {
      photo_id,
      bib_text: truncated ? p._bib.slice(1) : p._bib,
      confidence: truncated ? 0.42 : 0.93,
      rank: 0,
      crop_height: truncated ? 14 : 38,
      source: truncated ? 'ocr' : 'review',
    },
  ];
});

for (let i = 0; i < detections.length; i += 500) {
  const { error } = await db.from('detections').insert(detections.slice(i, i + 500));
  if (error) throw new Error(error.message);
}

log.ok(`${RUNNERS.length} runners, ${photos.length} photos, ${detections.length} detections`);
log.info('Try it: bib 1042, birthdate 14 · 03 · 1989');
