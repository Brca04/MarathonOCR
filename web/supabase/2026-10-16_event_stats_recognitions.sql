-- Landing page counters: add 'recognitions' (confirmed bib reads, one per
-- runner per photo). Run in the Supabase SQL editor, then rebuild the site:
--   cd web && node scripts/publish-event.mjs
-- Safe to run again.
create or replace function public.event_stats(p_event_slug text)
returns jsonb
language sql
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'ok', e.id is not null,
    'name', e.name,
    'edition', e.edition,
    'race_date', e.race_date,
    'city', e.city,
    'first_year', e.first_year,
    'finishers', (select count(*) from public.runners r
                   where r.event_id = e.id and r.status = 'finished'),
    -- Test photos (file names under _test/) and test runners (status 'test')
    -- open normally in a search but never count on the landing page.
    'photos', (select count(*) from public.photos p
                where p.event_id = e.id and p.file_name not like '\_test/%'),
    -- Runners with at least one photo that reads their bib exactly.
    'tagged_bibs', (select count(*) from public.runners r
                     where r.event_id = e.id
                       and r.status is distinct from 'test'
                       and exists (select 1 from public.detections d
                                     join public.photos p on p.id = d.photo_id
                                    where p.event_id = e.id and d.bib_text = r.bib)),
    -- Every confirmed bib read: one per runner per photo.
    'recognitions', (select count(*) from public.detections d
                      join public.photos p on p.id = d.photo_id
                     where p.event_id = e.id and d.source in ('review', 'manual')),
    'distance_km', (select max(distance_km) from public.races ra
                     where ra.event_id = e.id),
    'course_record', (select to_char(min(r.finish_time), 'FMHH24:MI:SS')
                        from public.runners r
                        join public.races ra on ra.id = r.race_id
                       where r.event_id = e.id and ra.code = 'marathon'
                         and r.status = 'finished')
  )
  from public.events e
  where e.slug = p_event_slug and e.published;
$$;
