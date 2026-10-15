-- Remove the test data before announcing the site (zagreb-2026):
--   runner 120404 "Test Trkač" (status 'test'),
--   photos _test/9999-1.jpg and _test/9999-2.jpg (they point at /brand/ images, nothing in R2),
--   their 2 'manual' tags for bib 120404.
-- Run the whole file at once in the Supabase SQL editor. It stops and changes
-- nothing if it would delete anything other than exactly 2 tags, 2 photos, 1 runner.
-- Afterwards: cd web && node scripts/publish-event.mjs
do $$
declare
  ev uuid;
  n_det int;
  n_photo int;
  n_runner int;
begin
  select id into ev from public.events where slug = 'zagreb-2026';

  delete from public.detections d
   using public.photos p
   where p.id = d.photo_id and p.event_id = ev and p.file_name like '\_test/%';
  get diagnostics n_det = row_count;

  delete from public.photos
   where event_id = ev and file_name like '\_test/%';
  get diagnostics n_photo = row_count;

  delete from public.runners
   where event_id = ev and bib = '120404' and status = 'test';
  get diagnostics n_runner = row_count;

  if n_det <> 2 or n_photo <> 2 or n_runner <> 1 then
    raise exception 'expected 2 tags, 2 photos, 1 runner; got %, %, % - nothing changed', n_det, n_photo, n_runner;
  end if;
  raise notice 'removed % tags, % photos, % runner', n_det, n_photo, n_runner;
end $$;
