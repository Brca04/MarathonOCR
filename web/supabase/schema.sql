-- ===========================================================================
-- Zagreb Marathon photo search — Supabase schema
--
-- Run this once in the Supabase SQL editor (or `supabase db push`).
-- Safe to re-run: everything is idempotent.
--
-- Two ideas carry the whole design:
--
--  1. Detections are candidates, not answers. The OCR pipeline stores *every*
--     reading it produced for a bib, with its confidence and rank. Matching a
--     runner to photos then happens at query time as exact ∪ edit-distance-1,
--     ranked by confidence × similarity. That is what turns 78.8% exact into
--     ~98.5% fuzzy@1 (see the repo README) without touching the model.
--
--  2. Birthdates never leave Postgres. `runners` is unreadable to the anon
--     key; the only way in is find_runner(), a SECURITY DEFINER function that
--     still holds the dob check but currently runs with it switched off — the
--     app passes a null p_dob, so a bib alone opens a gallery. Pass a date
--     again to turn verification back on. That is what lets the site be a
--     static export with no server of its own.
-- ===========================================================================

create extension if not exists pg_trgm;        -- trigram similarity + GIN index
create extension if not exists fuzzystrmatch;  -- levenshtein()
create extension if not exists "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Events and races
-- ---------------------------------------------------------------------------

create table if not exists public.events (
  id          uuid primary key default uuid_generate_v4(),
  slug        text not null unique,
  name        text not null,
  edition     int,
  race_date   date,
  city        text default 'Zagreb',
  -- Landing-page numbers that are editorial rather than derived.
  first_year  int,
  -- Gate for RLS: nothing is publicly readable until this flips.
  published   boolean not null default false,
  -- When the event is published as static files (export-static.mjs), turn the
  -- database search off so the only way to look up a bib is through the
  -- rate-limited edge. Leave true for events served straight from Postgres.
  db_search   boolean not null default true,
  created_at  timestamptz not null default now()
);

alter table public.events add column if not exists db_search boolean not null default true;

create table if not exists public.races (
  id          uuid primary key default uuid_generate_v4(),
  event_id    uuid not null references public.events(id) on delete cascade,
  code        text not null,               -- 'marathon' | 'half' | '10k'
  name        text not null,               -- 'Marathon'
  distance_km numeric(7,4) not null,       -- 42.1950
  unique (event_id, code)
);

-- ---------------------------------------------------------------------------
-- Runners — one row per bib per event. Contains PII; never exposed directly.
-- ---------------------------------------------------------------------------

create table if not exists public.runners (
  id             uuid primary key default uuid_generate_v4(),
  event_id       uuid not null references public.events(id) on delete cascade,
  race_id        uuid references public.races(id) on delete set null,
  bib            text not null,
  dob            date,                     -- the shared secret for the search
  full_name      text not null,
  gender         text,                     -- 'F' | 'M' | null
  category       text,                     -- 'W35', 'M45', …
  club           text,
  nationality    text,
  finish_time    interval,                 -- gun/official time
  chip_time      interval,
  place_overall  int,
  place_gender   int,
  place_category int,
  status         text default 'finished',  -- finished | dnf | dns | dsq
  created_at     timestamptz not null default now(),
  unique (event_id, bib)
);

create index if not exists runners_event_bib_idx on public.runners (event_id, bib);

-- Pace, derived — never stored, so it can never disagree with finish_time.
create or replace function public.runner_pace(p_time interval, p_km numeric)
returns text language sql immutable as $$
  select case
    when p_time is null or p_km is null or p_km = 0 then null
    else to_char(
      make_interval(secs => round(extract(epoch from p_time) / p_km)),
      'FMMI:SS')
  end;
$$;

-- ---------------------------------------------------------------------------
-- Photos and detections
-- ---------------------------------------------------------------------------

create table if not exists public.photos (
  id            uuid primary key default uuid_generate_v4(),
  event_id      uuid not null references public.events(id) on delete cascade,
  file_name     text not null,             -- as it came off the card / CSV
  -- Storage keys. `preview_path` is the public, watermarked, web-sized image;
  -- `original_path` sits in a private bucket and is only ever handed out as a
  -- short-lived signed URL.
  preview_path  text,
  thumb_path    text,                      -- small grid image; falls back to preview
  original_path text,
  width         int,
  height        int,
  captured_at   timestamptz,
  photographer  text,
  course_point  text,                      -- 'Start', '10K', 'Finish', …
  course_km     numeric(6,3),
  created_at    timestamptz not null default now(),
  unique (event_id, file_name)
);

create index if not exists photos_event_idx on public.photos (event_id);
alter table public.photos add column if not exists thumb_path text;

create table if not exists public.detections (
  id          uuid primary key default uuid_generate_v4(),
  photo_id    uuid not null references public.photos(id) on delete cascade,
  bib_text    text not null,               -- normalised digits, 2–6 chars
  confidence  numeric(5,4),                -- recognizer confidence, 0–1
  rank        int not null default 0,      -- 0 = top candidate for that crop
  bbox        jsonb,                       -- {x0,y0,x1,y1} in source pixels
  crop_height int,                         -- drives the accuracy bucket
  source      text not null default 'ocr'  -- 'ocr' | 'manual' | 'review'
);

-- The index that makes fuzzy search cheap. Trigrams on the candidate text.
create index if not exists detections_bib_trgm_idx
  on public.detections using gin (bib_text gin_trgm_ops);
create index if not exists detections_bib_idx on public.detections (bib_text);
create index if not exists detections_photo_idx on public.detections (photo_id);

-- ---------------------------------------------------------------------------
-- Purchases were removed. Clean up databases created by an earlier version.
-- ---------------------------------------------------------------------------

drop function if exists public.record_order(text, text, text, uuid, numeric);
drop table if exists public.orders;

-- ===========================================================================
-- Row level security
--
-- The anon key gets: nothing on runners, read-only on
-- photos and detections for published events. Everything else goes through
-- the two functions below.
-- ===========================================================================

alter table public.events     enable row level security;
alter table public.races      enable row level security;
alter table public.runners    enable row level security;
alter table public.photos     enable row level security;
alter table public.detections enable row level security;

drop policy if exists "events readable when published" on public.events;
create policy "events readable when published" on public.events
  for select using (published);

drop policy if exists "races readable when published" on public.races;
create policy "races readable when published" on public.races
  for select using (exists (
    select 1 from public.events e where e.id = races.event_id and e.published));

-- Photos and detections are NOT readable directly: the pair is a complete
-- bib -> photo index, and handing it to the anon key would let anyone download
-- every runner's gallery in one request. The app only ever reads them through
-- find_runner() (or the static export), both of which answer one bib at a time.
drop policy if exists "photos readable when published" on public.photos;
drop policy if exists "detections readable when published" on public.detections;

-- No policies on public.runners, photos or detections: with RLS on and no
-- permissive policy, anon and authenticated see zero rows. Deliberate.

-- ===========================================================================
-- find_runner — the only door into runner data
--
-- Returns null unless the bib exists in the event. Birthdate verification is
-- off for now: p_dob defaults to null and the check is skipped when it is,
-- so passing a date again is all it takes to bring it back.
-- On success returns the runner plus every photo whose detections point at
-- that bib, ranked by confidence × trigram similarity.
--
-- `match_kind` is carried through to the UI: 'exact' means a detection read
-- the bib verbatim, 'fuzzy' means it was one edit away. A false positive puts
-- a stranger in your gallery, so the two are never silently mixed.
-- ===========================================================================

create or replace function public.find_runner(
  p_event_slug text,
  p_bib        text,
  p_dob        date default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
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
  -- Static-published events are searched at the edge only (see db_search).
  -- Only browser callers (the anon/authenticated API roles) are turned away;
  -- export_event() under the service role and direct SQL are exempt. The role
  -- comes from the API request, since current_user here is the function owner.
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

  -- Only enforced when a date is supplied. The date is never echoed back.
  if p_dob is not null and v_runner.dob is distinct from p_dob then
    return jsonb_build_object('ok', false, 'reason', 'dob_mismatch');
  end if;

  select * into v_race from public.races where id = v_runner.race_id;

  -- Detections first, photos second. The candidate set is tiny (one bib and
  -- its one-edit neighbours), so this touches a handful of rows instead of
  -- every photo in the event — ~6x faster on a 20k-photo event.
  --
  -- Fuzzy matches are held to two rules, because a stranger's photo in your
  -- gallery is the worse failure:
  --   * the bib must have at least 3 digits (one edit on a 2-digit bib reaches
  --     a tenth of the field);
  --   * the misread must have been read with some conviction (>= 0.30) —
  --     below that it is mostly texture, not a half-read bib;
  --   * the misread must not itself be another runner's bib. When bibs are
  --     dense (1..400), "212" read on a photo is far more likely runner 212
  --     than a misread 213 — without this rule a typical gallery was 2 real
  --     photos and 27 of neighbours.
  with cand as (
    select d.photo_id,
           d.bib_text,
           coalesce(d.confidence, 0.5)
             * case when d.bib_text = v_bib then 1.0
                    else greatest(similarity(d.bib_text, v_bib), 0.2) end as score
      from public.detections d
      join public.photos ph on ph.id = d.photo_id and ph.event_id = v_event.id
     where d.bib_text = v_bib
        or (length(v_bib) >= 3
            and length(d.bib_text) between length(v_bib) - 1 and length(v_bib) + 1
            and levenshtein(d.bib_text, v_bib) <= 1
            and d.confidence >= 0.30
            and not exists (select 1 from public.runners r2
                             where r2.event_id = v_event.id and r2.bib = d.bib_text))
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
           -- How many different bibs are in this photo. The runner page opens on
           -- the photo with the fewest, where this runner is most likely the
           -- subject rather than one face in a crowd.
           'bibs_in_photo', (select count(distinct d2.bib_text)
                               from public.detections d2
                              where d2.photo_id = p.id)
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
$$;

revoke all on function public.find_runner(text, text, date) from public;
grant execute on function public.find_runner(text, text, date) to anon, authenticated;

-- ===========================================================================
-- export_event — every runner's find_runner() answer in one pass.
--
-- Used by scripts/export-static.mjs at publish time to write one small JSON
-- file per bib into the static site. Searches are then served from the CDN
-- and never reach the database, which is what lets the site take tens of
-- thousands of simultaneous visitors on the smallest Supabase instance.
-- Service role only: it would otherwise hand out the whole runner list.
-- ===========================================================================

create or replace function public.export_event(
  p_event_slug text,
  p_after_bib  text default '',
  p_limit      int  default 500
)
returns table (bib text, payload jsonb)
language sql
stable
security definer
set search_path = public
as $$
  select r.bib, public.find_runner(p_event_slug, r.bib, null)
    from public.runners r
    join public.events e on e.id = r.event_id
   where e.slug = p_event_slug and e.published
     and r.bib > p_after_bib
   order by r.bib
   limit p_limit;
$$;

revoke all on function public.export_event(text, text, int) from public, anon, authenticated;

-- ===========================================================================
-- event_stats — the landing page counters. Aggregates only, no PII.
-- ===========================================================================

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
    'photos', (select count(*) from public.photos p where p.event_id = e.id),
    -- Runners with at least one photo that reads their bib exactly.
    'tagged_bibs', (select count(*) from public.runners r
                     where r.event_id = e.id
                       and exists (select 1 from public.detections d
                                     join public.photos p on p.id = d.photo_id
                                    where p.event_id = e.id and d.bib_text = r.bib)),
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

revoke all on function public.event_stats(text) from public;
grant execute on function public.event_stats(text) to anon, authenticated;

-- ===========================================================================
-- Storage buckets
-- ===========================================================================

insert into storage.buckets (id, name, public)
values ('race-previews', 'race-previews', true)
on conflict (id) do update set public = true;

insert into storage.buckets (id, name, public)
values ('race-originals', 'race-originals', false)
on conflict (id) do nothing;

drop policy if exists "previews are public" on storage.objects;
create policy "previews are public" on storage.objects
  for select using (bucket_id = 'race-previews');
