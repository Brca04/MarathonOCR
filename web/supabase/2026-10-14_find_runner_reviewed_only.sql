-- A photo a person reviewed matches only the numbers they confirmed
-- (source 'review' / 'manual'). The model's other reads on that photo,
-- including ones the reviewer removed, no longer match exactly or fuzzily.
-- Photos nobody reviewed keep the old behaviour (OCR reads, fuzzy tier).
-- source 'rejected': reads on a photo a reviewer marked as having no bib.
CREATE OR REPLACE FUNCTION public.find_runner(p_event_slug text, p_bib text, p_dob date DEFAULT NULL::date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  v_event  public.events;
  v_runner public.runners;
  v_race   public.races;
  v_bib    text := regexp_replace(coalesce(p_bib, ''), '\D', '', 'g');
  v_photos jsonb;
begin
  if v_bib = '' then
    return jsonb_build_object('ok', false, 'reason', 'missing_input');
  end if;

  select * into v_event from public.events
   where slug = p_event_slug and published;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'no_event');
  end if;
  if not v_event.db_search
     and coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'role', '')
         in ('anon', 'authenticated') then
    return jsonb_build_object('ok', false, 'reason', 'no_event');
  end if;

  select * into v_runner from public.runners
   where event_id = v_event.id and bib = v_bib;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'no_bib');
  end if;

  if p_dob is not null and v_runner.dob is distinct from p_dob then
    return jsonb_build_object('ok', false, 'reason', 'dob_mismatch');
  end if;

  select * into v_race from public.races where id = v_runner.race_id;

  with cand as (
    select d.photo_id,
           d.bib_text,
           coalesce(d.confidence, 0.5)
             * case when d.bib_text = v_bib then 1.0
                    else greatest(similarity(d.bib_text, v_bib), 0.2) end as score
      from public.detections d
      join public.photos ph on ph.id = d.photo_id and ph.event_id = v_event.id
     where d.source <> 'rejected'
       and (d.source in ('review', 'manual')
            or not exists (select 1 from public.detections dr
                            where dr.photo_id = d.photo_id
                              and dr.source in ('review', 'manual')))
       and (d.bib_text = v_bib
        or (d.source not in ('review', 'manual')
            and length(v_bib) >= 3
            and length(d.bib_text) between length(v_bib) - 1 and length(v_bib) + 1
            and levenshtein(d.bib_text, v_bib) <= 1
            and d.confidence >= 0.30
            and not exists (select 1 from public.runners r2
                             where r2.event_id = v_event.id and r2.bib = d.bib_text)))
  ),
  best as (
    select distinct on (c.photo_id)
           c.photo_id, c.bib_text, c.score,
           case when c.bib_text = v_bib then 'exact' else 'fuzzy' end as match_kind
      from cand c
     order by c.photo_id, (c.bib_text = v_bib) desc, c.score desc
  )
  select coalesce(jsonb_agg(jsonb_build_object(
           'id',            p.id,
           'file_name',     p.file_name,
           'preview_path',  p.preview_path,
           'thumb_path',    p.thumb_path,
           'width',         p.width,
           'height',        p.height,
           'captured_at',   p.captured_at,
           'photographer',  p.photographer,
           'course_point',  p.course_point,
           'course_km',     p.course_km,
           'match_kind',    b.match_kind,
           'match_score',   round(b.score::numeric, 4),
           'read_as',       b.bib_text,
           'bibs_in_photo', coalesce(
                              nullif((select count(distinct d2.bib_text)
                                        from public.detections d2
                                       where d2.photo_id = p.id
                                         and d2.source in ('review', 'manual')), 0),
                              (select count(distinct d2.bib_text)
                                 from public.detections d2
                                where d2.photo_id = p.id))
         ) order by p.course_km nulls last, p.captured_at nulls last, p.file_name), '[]'::jsonb)
    into v_photos
    from best b
    join public.photos p on p.id = b.photo_id
   where p.event_id = v_event.id;

  return jsonb_build_object(
    'ok', true,
    'runner', jsonb_build_object(
      'bib',            v_runner.bib,
      'name',           v_runner.full_name,
      'category',       v_runner.category,
      'club',           v_runner.club,
      'nationality',    v_runner.nationality,
      'race',           coalesce(v_race.name, 'Marathon'),
      'race_code',      coalesce(v_race.code, 'marathon'),
      'distance_km',    coalesce(v_race.distance_km, 42.195),
      'status',         v_runner.status,
      'time',           case when v_runner.finish_time is null then null
                             else to_char(v_runner.finish_time, 'FMHH24:MI:SS') end,
      'pace',           public.runner_pace(v_runner.finish_time,
                                           coalesce(v_race.distance_km, 42.195)),
      'place_overall',  v_runner.place_overall,
      'place_category', v_runner.place_category
    ),
    'photos', v_photos
  );
end;
$function$;
