-- Take Vedran's and Omar's photos with no confirmed bib off the site
-- (reviewers marked them "no bib"). Expected: Vedran Metelko 23, Omar Mocic 2.
-- Deleting a photo row also deletes its detections (on delete cascade). The
-- R2 files stay but can't be reached without a row.
-- Run part 1, check the numbers, then run part 2. Then rebuild:
--   cd web && node scripts\publish-event.mjs

-- 1. Preview: which photos would go (changes nothing)
select p.photographer, count(*) as photos, string_agg(p.file_name, ', ' order by p.file_name) as files
  from public.photos p
  join public.events e on e.id = p.event_id and e.slug = 'zagreb-2026'
 where p.photographer in ('Vedran Metelko', 'Omar Mocic')
   and not exists (select 1 from public.detections d
                    where d.photo_id = p.id and d.source in ('review', 'manual'))
 group by 1 order by 1;

-- 2. Delete them
delete from public.photos p
 using public.events e
 where e.id = p.event_id and e.slug = 'zagreb-2026'
   and p.photographer in ('Vedran Metelko', 'Omar Mocic')
   and not exists (select 1 from public.detections d
                    where d.photo_id = p.id and d.source in ('review', 'manual'));
